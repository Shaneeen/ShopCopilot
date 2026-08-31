#!/usr/bin/env python3
"""Bench v1.0 — targeted retrieval test, now 100 cases (10/10/30/50) with batched APIs.

Each case anchors to a single parent_asin from the 50k catalog with scripted
multi-turn conversation. 4-difficulty stratified: 10 easy / 10 medium / 30 hard /
50 insane. Batched parallel execution: cases run concurrently via ThreadPool,
so LLM API calls overlap instead of serial per-turn, cutting wall time ~workers×.

Text model only (no vision). LLM is 30-shortlist reranker, not 200 chooser.

    python scripts/bench_v1.py                              # 4-case quick offline demo
    python scripts/bench_v1.py --cases 100 --seed 7         # 100-case full (default)
    python scripts/bench_v1.py --cases 100 --workers 8      # parallel, batched
    python scripts/bench_v1.py --cases 100 --live --workers 8 --batch-size 16
    OPENROUTER_API_KEY=... python scripts/bench_v1.py --cases 100 --live --workers 8
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("NEESHOPS_LOG_LEVEL", "ERROR")

from neeshops.config.settings import load_strategy
from neeshops.ranking.heuristic import HeuristicRanker
from neeshops.ranking.llm_reranker import LLMReranker
from neeshops.ranking.providers.fake import FakeRankingProvider

CATALOG = Path("data/catalog.jsonl")

PRICING = {
    "nvidia/nemotron-3-super-120b-a12b:free": (0.0, 0.0),
    "nvidia/nemotron-3-super-120b-a12b": (0.085, 0.40),
    "nvidia/nemotron-3.5-lightning:free": (0.0, 0.0),
    "liquidai/lfm-2.5-2.6b:free": (0.0, 0.0),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.00),
    "openai/gpt-3.5-turbo": (0.50, 1.50),
    "google/gemini-flash-1.5": (0.075, 0.30),
    "google/gemini-2.0-flash-001": (0.10, 0.40),
    "gemini-3.7-flash": (0.10, 0.40),
    "anthropic/claude-3-haiku": (0.25, 1.25),
    "fake": (0.15, 0.60),
    "heuristic": (0.0, 0.0),
}


def est_cost(model: str, pt: int, ct: int) -> float:
    inp, out = PRICING.get(model, PRICING.get(model.split("/")[-1], (0.15, 0.60)))
    return round(pt / 1_000_000 * inp + ct / 1_000_000 * out, 6)


@dataclass(frozen=True)
class Case:
    id: str
    difficulty: str
    target: str
    turns: list[str]
    notes: str


ANCHOR_BENCH: list[Case] = [
    Case(
        "easy-1",
        "easy",
        "B07KCFS4VC",
        [
            "I need a t-shirt for everyday wear",
            "Something from Columbia, crew neck style",
            "The Thistletown Park Crew, men's, size M",
        ],
        "Mimics public easy (buying): starts vague category, then brand+product, then size — 2 clarifications.",
    ),
    Case(
        "medium-1",
        "medium",
        "B095PZG4SR",
        [
            "I'm looking for socks for running",
            "Women's athletic, cushioned and moisture wicking, low cut",
            "Lycra material, Hylaea brand preferred, under $30",
        ],
        "Mimics public medium (browsing): vague → feature → brand+budget.",
    ),
    Case(
        "hard-1",
        "hard",
        "B08VDM4G8B",
        [
            "I need something for a Halloween party",
            "Actually a costume, jackets section — but I'm still browsing",
            "Pink, 1950s style with scarf, women's",
            "Under $25, but I don't have a preference for material",
        ],
        "Mimics public hard (intent-override + boundary): vague → override browsing→buying → NO_PREFERENCE.",
    ),
    Case(
        "insane-1",
        "insane",
        "B07K34RX5J",
        [
            "gift for someone maybe",
            "maybe earrings artsy lightweight",
            "fabric not metal please",
            "NO_PREFERENCE size brand",
            "hypoallergenic stainless hooks",
            "birthday gift artsy style",
        ],
        "Harder than public: 6 turns, 5-word max, vague → intent-override → NO_PREFERENCE, sparse catalog.",
    ),
]


def load_lookup(path: Path) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            lookup[str(r["parent_asin"])] = r
    return lookup


def _keywords_from_row(row: dict, limit: int = 8) -> list[str]:
    title = str(row.get("title", "")).split()
    cats = [str(c) for c in (row.get("categories") or []) if str(c).strip()]
    feats = [str(c) for c in (row.get("features") or []) if str(c).strip()]
    toks: list[str] = []
    for w in title[:6]:
        if len(w) > 2:
            toks.append(w)
    if cats:
        toks.append(cats[0])
    if feats:
        toks.append(feats[0][:40])
    return toks[:limit]


def build_bench_cases(
    catalog_path: Path,
    n: int,
    seed: int,
    distribution: tuple[int, int, int, int] | None = None,
) -> list[Case]:
    if n == 4:
        return ANCHOR_BENCH
    if distribution is None:
        if n == 100:
            distribution = (10, 10, 30, 50)
        else:
            e = max(1, round(n * 0.1))
            m = max(1, round(n * 0.1))
            h = max(1, round(n * 0.3))
            ins = n - e - m - h
            distribution = (e, m, h, ins)
    if sum(distribution) != n:
        raise ValueError(f"distribution {distribution} must sum to {n}")
    lookup = load_lookup(catalog_path)
    all_rows = list(lookup.values())
    rng = random.Random(seed)
    # Filter to rows with title and asin for quality
    candidates = [
        r
        for r in all_rows
        if str(r.get("title", "")).strip() and str(r.get("parent_asin", "")).strip()
    ]
    # Weight hard/insane toward sparser / lower-rating rows to make them genuinely harder
    candidates_sorted = sorted(
        candidates,
        key=lambda r: (
            len(str(r.get("features") or "")),
            int(r.get("rating_number") or 0),
        ),
    )
    easy_pool = [
        r
        for r in candidates
        if len(str(r.get("features") or "")) > 200
        and int(r.get("rating_number") or 0) > 500
    ][:5000]
    medium_pool = candidates[::3]
    hard_pool = candidates_sorted[:15000]
    insane_pool = candidates_sorted[:5000]
    pools = {
        "easy": easy_pool,
        "medium": medium_pool,
        "hard": hard_pool,
        "insane": insane_pool,
    }
    counts = dict(zip(["easy", "medium", "hard", "insane"], distribution))
    # Reserve anchors so 100-case includes them for continuity
    bench: list[Case] = []
    used: set[str] = set()
    for c in ANCHOR_BENCH:
        bench.append(c)
        used.add(c.target)
        counts[c.difficulty] -= 1

    def turns_for(row: dict, diff: str, idx: int) -> list[str]:
        title = str(row.get("title", ""))[:80]
        kws = _keywords_from_row(row)
        cats = [str(c) for c in (row.get("categories") or []) if str(c).strip()]
        cat = cats[0].lower() if cats else "item"
        feats = [str(c) for c in (row.get("features") or []) if str(c).strip()]
        price = row.get("price")
        brand = str(row.get("store", ""))[:20] if row.get("store") else ""
        if diff == "easy":
            return [
                f"I need a {cat} for everyday wear",
                f"Something like {title[:50]}"
                if len(title) > 20
                else f"Maybe {kws[0] if kws else cat}",
                f"{brand + ', ' if brand else ''}{kws[0] if kws else title[:40]}, size M"
                if brand
                else f"{title[:60]}, size M",
            ]
        if diff == "medium":
            return [
                f"I'm looking for a {cat}, something comfortable",
                f"{' '.join(kws[:3])} — {feats[0][:40] if feats else 'good quality'}",
                # Exact price (mirrors the official evaluator's "budget
                # around $X"): price+5 broke the 1.10x budget tolerance for
                # targets under $50 and hard-dropped them from the pool.
                f"Prefer {brand + ' ' if brand else ''}{kws[1] if len(kws) > 1 else cat}, under ${int(price) if isinstance(price, (int, float)) else 40}",
            ]
        if diff == "hard":
            return [
                f"I need something for a party, not sure what yet",
                f"Actually {cat} section, {kws[0] if kws else cat} style — still browsing",
                f"{' '.join(kws[:3])} in {cat}, {kws[2] if len(kws) > 2 else cat}",
                "Under $30, but I don't have a preference for material",
            ]
        # insane: 6 turns, 5 words max each — less context, way harder than public set
        w2 = (kws[1] if len(kws) > 1 else "nice").split()[0][:12]
        cat_word = cat.split(",")[0].split()[0][:12]
        return [
            "gift for someone maybe",
            f"maybe {cat_word} {w2}",
            f"{w2} not other material",
            "NO_PREFERENCE size brand",
            "hypoallergenic stainless hooks",
            "birthday gift artsy style",
        ]

    for diff in ["easy", "medium", "hard", "insane"]:
        need = counts[diff]
        pool = pools[diff]
        rng.shuffle(pool)
        added = 0
        for row in pool:
            asin = str(row["parent_asin"])
            if asin in used:
                continue
            idx = len([c for c in bench if c.difficulty == diff]) + 1
            bench.append(
                Case(
                    f"{diff}-{idx}",
                    diff,
                    asin,
                    turns_for(row, diff, idx),
                    f"Auto-generated {diff} from catalog (seed {seed})",
                )
            )
            used.add(asin)
            added += 1
            if added >= need:
                break
    rng.shuffle(bench)
    return bench


_LOOKUP_CACHE: dict[str, dict] = {}


def _heuristic_worker(task):
    catalog_str, case, label, verbose, model_name = task
    catalog = Path(catalog_str)
    strategy = load_strategy()
    agent = _make_agent(catalog, strategy, HeuristicRanker(strategy=strategy))
    res = run_case(agent, case, label, verbose=verbose)
    res["est_cost_usd"] = est_cost(model_name, res["total_pt"], res["total_ct"])
    res["model"] = model_name
    return res


def _make_agent(catalog: Path, strategy: dict, ranker):
    from neeshops.agent import NeeShopsAgent
    from neeshops.retrieval.bm25 import BM25Retriever
    from neeshops.retrieval.hybrid import HybridRetriever
    from neeshops.utils.catalog import load_catalog_lookup

    bm25 = BM25Retriever(catalog_path=catalog)
    retriever = HybridRetriever(bm25=bm25, strategy=strategy)
    # One catalog parse per path for the whole bench (the lookup is read-
    # only downstream; building a fresh agent per case must not re-parse
    # 50k JSONL rows every time).
    key = str(catalog.resolve())
    lookup = _LOOKUP_CACHE.get(key)
    if lookup is None:
        lookup = load_catalog_lookup(catalog)
        _LOOKUP_CACHE[key] = lookup
    impl = NeeShopsAgent(
        retriever=retriever, ranker=ranker, catalog_lookup=lookup, strategy=strategy
    )

    class _Shim:
        def __init__(self, impl):
            self._impl = impl

        def reset(self, sid, user_profile=None, **kw):
            if user_profile is None:
                user_profile = kw.get("user_profile", {})
            return self._impl.reset(sid, user_profile)

        def respond(self, sid, msg, turn, top_k):
            r = self._impl.respond(sid, msg, turn, top_k)
            return {
                "message": r["message"],
                "ask_attribute": r.get("ask_attribute"),
                "recommendations": r.get("recommendations", []),
                "usage": r.get("usage", {"prompt_tokens": 0, "completion_tokens": 0}),
            }

    return _Shim(impl)


def make_agent_factories(
    catalog: Path, live: bool, model: str, secondary: str, arms: str = "all"
) -> dict[str, tuple[Any, str]]:
    factories: dict[str, tuple[Any, str]] = {}

    def _want(name: str) -> bool:
        if arms == "all":
            return True
        return name in {a.strip() for a in arms.split(",")}

    def heuristic_factory():
        strategy = load_strategy()
        return _make_agent(catalog, strategy, HeuristicRanker(strategy=strategy))

    if _want("no-llm"):
        factories["no-llm (heuristic)"] = (heuristic_factory, "heuristic")

    def fake_factory():
        strategy = load_strategy()
        return _make_agent(
            catalog,
            strategy,
            LLMReranker(
                provider=FakeRankingProvider(
                    [], prompt_tokens=420, completion_tokens=18
                ),
                strategy=strategy,
                enabled=True,
            ),
        )

    if _want("fake-llm"):
        factories["fake-llm (simulated openrouter text)"] = (fake_factory, "fake")

    if live:
        if (
            os.getenv("OPENROUTER_API_KEY")
            or os.getenv("NEESHOPS_LLM_PROVIDER") == "openrouter"
        ):

            def openrouter_factory():
                from neeshops.ranking.providers.openrouter import (
                    OpenRouterRankingProvider,
                )

                strategy = load_strategy()
                return _make_agent(
                    catalog,
                    strategy,
                    LLMReranker(
                        provider=OpenRouterRankingProvider(model=model),
                        strategy=strategy,
                        enabled=True,
                    ),
                )

            factories[f"openrouter:{model}"] = (openrouter_factory, model)
        if os.getenv("GEMINI_API_KEY"):

            def gemini_factory():
                from neeshops.ranking.providers.gemini import GeminiRankingProvider

                strategy = load_strategy()
                return _make_agent(
                    catalog,
                    strategy,
                    LLMReranker(
                        provider=GeminiRankingProvider(model=secondary),
                        strategy=strategy,
                        enabled=True,
                    ),
                )

            factories[f"gemini:{secondary}"] = (gemini_factory, secondary)
    return factories


def run_case(agent, case: Case, model_label: str, verbose: bool) -> dict[str, Any]:
    sid = f"bench_{case.id}_{model_label}_{random.randint(0, 1_000_000)}"
    agent.reset(sid, user_profile={"preference_tags": []})
    total_pt = 0
    total_ct = 0
    latencies: list[float] = []
    llm_lats: list[float] = []
    llm_calls = 0
    fallback_reasons: list[str | None] = []
    last_recs: list[str] = []
    hit_rank: int | None = None
    hit_turn: int | None = None

    for idx, msg in enumerate(case.turns, start=1):
        t0 = time.perf_counter()
        resp = agent.respond(sid, msg, idx, 10)
        dt = (time.perf_counter() - t0) * 1000
        latencies.append(dt)
        usage = resp.get("usage") or {}
        total_pt += int(usage.get("prompt_tokens") or 0)
        total_ct += int(usage.get("completion_tokens") or 0)
        imp = agent._impl
        fb = getattr(imp.ranker, "last_fallback_reason", None)
        llm_ms = getattr(imp.ranker, "last_latency_ms", 0.0)
        if isinstance(llm_ms, (int, float)) and llm_ms > 0:
            llm_lats.append(float(llm_ms))
            llm_calls += 1
        fallback_reasons.append(fb)
        recs = [r["parent_asin"] for r in resp.get("recommendations") or []]
        last_recs = recs
        if case.target in recs and hit_rank is None:
            hit_rank = recs.index(case.target) + 1
            hit_turn = idx
        if verbose:
            mark = f" HIT@{hit_rank}" if case.target in recs else ""
            print(
                f"    turn {idx} latency={dt:.1f}ms llm={llm_ms:.1f}ms fb={fb} usage={usage}{mark}"
            )

    hit = hit_rank is not None
    rr = 0.0 if hit_rank is None else 1.0 / hit_rank
    return {
        "case": case.id,
        "difficulty": case.difficulty,
        "target": case.target,
        "hit": hit,
        "rank": hit_rank,
        "hit_turn": hit_turn,
        "rr": rr,
        "recs": last_recs[:10],
        "avg_latency_ms": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        "p50_latency_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
        "avg_llm_ms": round(statistics.fmean(llm_lats), 1) if llm_lats else 0.0,
        "llm_calls": llm_calls,
        "total_pt": total_pt,
        "total_ct": total_ct,
        "fallbacks": fallback_reasons,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Bench v1.0 — 100-case (10/10/30/50) batched"
    )
    ap.add_argument("--catalog", default="data/catalog.jsonl")
    ap.add_argument(
        "--cases", type=int, default=100, help="4 for quick demo, 100 for full"
    )
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--live", action="store_true", help="also run real providers if keys present"
    )
    ap.add_argument("--model", default="nvidia/nemotron-3-super-120b-a12b:free")
    ap.add_argument("--secondary", default="gemini-3.7-flash")
    ap.add_argument(
        "--workers", type=int, default=8, help="parallel cases (batch API calls)"
    )
    ap.add_argument(
        "--batch-size", type=int, default=16, help="not used for OpenRouter but logged"
    )
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", default="evaluation/results/bench_v1.json")
    ap.add_argument(
        "--arms",
        default="all",
        help="comma subset of arms to run: no-llm,fake-llm (default all)",
    )
    args = ap.parse_args()

    catalog = Path(args.catalog)
    if not catalog.exists():
        for alt in [
            Path("C:/Users/Lenovo/Downloads/TIktok TechJam 2026/catalog.jsonl"),
            Path("../catalog.jsonl"),
        ]:
            if alt.exists():
                catalog = alt
                break

    bench = build_bench_cases(catalog, n=args.cases, seed=args.seed)
    print(
        f"Bench v1.0: {len(bench)} cases (seed {args.seed}) — "
        + ", ".join(
            f"{d}:{sum(1 for c in bench if c.difficulty == d)}"
            for d in ["easy", "medium", "hard", "insane"]
        )
        + f" | workers={args.workers} batch={args.batch_size}"
    )
    lookup = load_lookup(catalog)
    factories = make_agent_factories(
        catalog,
        live=args.live,
        model=args.model,
        secondary=args.secondary,
        arms=args.arms,
    )
    all_results: dict[str, Any] = {
        "cases": [c.__dict__ for c in bench],
        "meta": {
            "cases": args.cases,
            "seed": args.seed,
            "workers": args.workers,
            "batch_size": args.batch_size,
        },
        "arms": {},
    }

    for label, (factory, model_name) in factories.items():
        print(f"\n=== arm: {label} ===")
        is_fake = "fake" in label
        t_arm_start = time.perf_counter()
        cases_out: list[dict[str, Any]] = []

        def _run_one(case: Case):
            agent = factory()
            if is_fake:
                agent._impl.ranker = LLMReranker(
                    provider=FakeRankingProvider(
                        [case.target], prompt_tokens=420, completion_tokens=18
                    ),
                    strategy=load_strategy(),
                    enabled=True,
                )
                agent._impl.ranker._secondary_provider = None
            res = run_case(agent, case, label, verbose=args.verbose)
            res["est_cost_usd"] = est_cost(model_name, res["total_pt"], res["total_ct"])
            res["model"] = model_name
            return res

        is_cpu_arm = "heuristic" in label or label.startswith("no-llm")
        if is_cpu_arm:
            with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as ex:
                tasks = [
                    (str(catalog), case, label, args.verbose, model_name)
                    for case in bench
                ]
                future_to_case = {ex.submit(_heuristic_worker, t): t[1] for t in tasks}
                done = 0
                for fut in concurrent.futures.as_completed(future_to_case):
                    case = future_to_case[fut]
                    try:
                        res = fut.result()
                    except Exception as e:
                        print(f"  [ERR] {case.id} {e}")
                        continue
                    cases_out.append(res)
                    done += 1
                    if not args.verbose and done % 20 == 0:
                        print(f"  ... {done}/{len(bench)} cases done")
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
                future_to_case = {ex.submit(_run_one, case): case for case in bench}
                done = 0
                for fut in concurrent.futures.as_completed(future_to_case):
                    case = future_to_case[fut]
                    try:
                        res = fut.result()
                    except Exception as e:
                        print(f"  [ERR] {case.id} {e}")
                        continue
                    cases_out.append(res)
                    done += 1
                    if not args.verbose and done % 20 == 0:
                        print(f"  ... {done}/{len(bench)} cases done")

        # Keep original bench order for reporting
        order = {c.id: i for i, c in enumerate(bench)}
        cases_out.sort(key=lambda r: order.get(r["case"], 999))

        for res in cases_out[:5]:
            row_lookup = lookup.get(res["target"], {})
            title = str(row_lookup.get("title", ""))[:55]
            status = f"HIT@{res['rank']}" if res["hit"] else "MISS"
            print(
                f"  [{res['difficulty']:<7} {status:<9}] {res['case']} target={res['target']} lat={res['avg_latency_ms']}ms tokens {res['total_pt']}+{res['total_ct']} cost ${res['est_cost_usd']:.6f} | {title}"
            )
        if len(cases_out) > 5:
            print(f"  ... ({len(cases_out) - 5} more cases)")

        hit_rate = (
            sum(1 for c in cases_out if c["hit"]) / len(cases_out) if cases_out else 0
        )
        mrr = statistics.fmean(c["rr"] for c in cases_out) if cases_out else 0
        avg_lat = (
            round(statistics.fmean(c["avg_latency_ms"] for c in cases_out), 1)
            if cases_out
            else 0
        )
        p50_lat = (
            round(statistics.median(c["p50_latency_ms"] for c in cases_out), 1)
            if cases_out
            else 0
        )
        avg_llm = round(
            statistics.fmean(
                [c["avg_llm_ms"] for c in cases_out if c["avg_llm_ms"] > 0] or [0]
            ),
            1,
        )
        tot_pt = sum(c["total_pt"] for c in cases_out)
        tot_ct = sum(c["total_ct"] for c in cases_out)
        tot_calls = sum(c["llm_calls"] for c in cases_out)
        tot_cost = round(sum(c["est_cost_usd"] for c in cases_out), 6)
        wall = time.perf_counter() - t_arm_start
        by_diff = {}
        for d in ["easy", "medium", "hard", "insane"]:
            subset = [c for c in cases_out if c["difficulty"] == d]
            if subset:
                by_diff[d] = {
                    "hit_rate": round(
                        sum(1 for c in subset if c["hit"]) / len(subset), 3
                    ),
                    "mrr": round(statistics.fmean(c["rr"] for c in subset), 3),
                    "n": len(subset),
                }

        summary = {
            "hit_rate@10": round(hit_rate, 3),
            "mrr": round(mrr, 3),
            "avg_latency_ms": avg_lat,
            "p50_latency_ms": p50_lat,
            "avg_llm_ms": avg_llm,
            "llm_calls": tot_calls,
            "total_prompt_tokens": tot_pt,
            "total_completion_tokens": tot_ct,
            "est_cost_usd": tot_cost,
            "wall_seconds": round(wall, 1),
            "model": model_name,
            "by_difficulty": by_diff,
        }
        all_results["arms"][label] = {"cases": cases_out, "summary": summary}
        print(
            f"  -> summary hit {summary['hit_rate@10']} mrr {summary['mrr']} avg_lat {avg_lat}ms p50 {p50_lat}ms llm {avg_llm}ms calls {tot_calls} tokens {tot_pt}+{tot_ct} cost ${tot_cost:.6f} wall {wall:.1f}s"
        )
        for d in ["easy", "medium", "hard", "insane"]:
            if d in by_diff:
                print(
                    f"     {d:<7} hit {by_diff[d]['hit_rate']} mrr {by_diff[d]['mrr']} n={by_diff[d]['n']}"
                )

    print("\n=== bench v1.0 cross-arm table (100-case) ===")
    header = f"{'arm':<38} {'hit':<6} {'mrr':<6} {'avg_ms':<7} {'p50':<7} {'llm_ms':<7} {'calls':<5} {'pt':<7} {'ct':<6} {'cost $':<10} {'wall s':<7}"
    print(header)
    print("-" * len(header))
    for label, data in all_results["arms"].items():
        s = data["summary"]
        print(
            f"{label:<38} {s['hit_rate@10']:<6} {s['mrr']:<6} {s['avg_latency_ms']:<7} {s['p50_latency_ms']:<7} {s['avg_llm_ms']:<7} {s['llm_calls']:<5} {s['total_prompt_tokens']:<7} {s['total_completion_tokens']:<6} {s['est_cost_usd']:<10} {s['wall_seconds']:<7}"
        )

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(
        f"\nwrote {out} | cases={args.cases} workers={args.workers} batch={args.batch_size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
