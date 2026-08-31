#!/usr/bin/env python3
"""Oracle product-guessing eval: a simulated customer 'knows' a randomly
sampled target product from the 50k catalog and answers the agent's
clarification questions truthfully from that product's own fields.

Mirrors the official evaluator protocol (evaluator/local_evaluator.py):
MAX_TURNS=10, TOP_K=10, the same customer reply style, and the same metric
family (Hit@10, MRR, MTTC) — but samples targets at random from the whole
catalog instead of the public set, so it measures generalisation without
touching the scored set. Also instruments the P2 200-candidate contract:
per turn it reports whether the target survived BM25+semantic retrieval
(pool@200) and metadata filtering (filtered@200).

    python scripts/run_oracle_eval.py --strategy both --cases 30 --seed 7
    python scripts/run_oracle_eval.py --strategy baseline --verbose

Strategies:
  baseline — pre-improvement clarification config (2 fixed-order questions,
             no slot-filling context)
  adaptive — improved config (slot-filling + pool-aware question selection)
  both     — run the identical seeded case list under each and diff
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from pathlib import Path

# Structured pipeline logs are noise for an eval harness — quiet them
# before any neeshops module configures logging.
os.environ.setdefault("NEESHOPS_LOG_LEVEL", "ERROR")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluator.local_evaluator import (  # noqa: E402
    MAX_TURNS,
    TOP_K,
    coarse_category,
    customer_reply,
    initial_message,
    intent_card,
)
from neeshops.config.settings import load_strategy  # noqa: E402
from neeshops.conversation.constraints import extract_constraints  # noqa: E402
from neeshops.retrieval.filters import apply_filters  # noqa: E402
from starter.agent import Agent  # noqa: E402

BASELINE_CLARIFICATION = {
    "max_questions_per_session": 2,
    "min_candidates_before_recommend": 5,
    "ask_if_candidates_above": 60,
}

CATEGORY_SKIP = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}


def load_catalog(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json_loads(line)
                if row.get("title"):
                    rows.append(row)
    return rows


def json_loads(line: str) -> dict:
    import json

    return json.loads(line)


def sample_targets(rows: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    return rng.sample(rows, n)


def pool_diagnostics(agent: Agent, session_id: str, message: str, target: str) -> dict:
    """Replicate the agent's own candidate pipeline for this message (pre-
    turn state) and report where the target stands in the 200-candidate
    contract: raw retrieval rank, post-guarantee/post-filter pool rank."""
    impl = agent._impl
    state = impl.state_manager.get(session_id)
    slot = state.history[-1].asked_attribute if state.history else None
    extracted = extract_constraints(message, slot=slot)
    preview = impl._preview_state(state, extracted)
    queries = impl.build_retrieval_queries(state, message, extracted)
    limit = int(impl.strategy["retrieval"].get("candidate_limit", 200))
    hybrid = impl.retriever.search_multi(queries, state, top_k=limit)
    retrieval_rank = next(
        (i + 1 for i, c in enumerate(hybrid) if c.parent_asin == target), None
    )
    info = impl._guarantee_info(preview)
    pool = impl._priority_union(hybrid, info, limit)
    pool = apply_filters(
        pool, impl.catalog_lookup, preview, token_index=impl.token_index
    )
    pool = impl._topup_pool(pool, preview, info, limit)
    pool_rank = next(
        (i + 1 for i, c in enumerate(pool) if c.parent_asin == target), None
    )
    return {
        "pool_size": len(pool),
        "retrieval_rank": retrieval_rank,
        "pool_rank": pool_rank,
        "filtered_rank": pool_rank,
        "and_set_size": info.get("and_set_size"),
        "over_generality": info.get("over_generality", False),
    }


def run_case(
    agent: Agent, target_row: dict, case_idx: int, verbose: bool, diag: bool = False
) -> dict:
    target = str(target_row["parent_asin"])
    card = intent_card(target_row)
    categories = [str(c) for c in target_row.get("categories") or []]
    session_id = f"oracle_{case_idx}"
    agent.reset(session_id, user_profile={"preference_tags": []})

    disclosed: set[str] = set()
    message = initial_message(
        {"scenario_type": "buying", "intent_card": card},
        coarse_category(categories),
        disclosed,
    )

    first_hit_turn = None
    best_rank = None
    pool_hits = 0
    filter_kills = 0
    pool_sizes = []
    latencies = []

    for turn in range(1, MAX_TURNS + 1):
        diag_info = (
            pool_diagnostics(agent, session_id, message, target)
            if diag
            else {
                "pool_size": 0,
                "pool_rank": None,
                "filtered_rank": None,
                "and_set_size": None,
                "over_generality": False,
            }
        )
        pool_sizes.append(diag_info["pool_size"])
        if diag_info["pool_rank"] is not None:
            pool_hits += 1
            if diag_info["filtered_rank"] is None:
                filter_kills += 1

        start = time.perf_counter()
        response = agent.respond(session_id, message, turn, TOP_K)
        latencies.append((time.perf_counter() - start) * 1000)

        ranked = [r["parent_asin"] for r in response["recommendations"]][:TOP_K]
        if verbose:
            mark = ""
            if target in ranked:
                mark = f"  <<< TARGET at rank {ranked.index(target) + 1}"
            print(
                f"    t{turn} asked={response.get('ask_attribute')!r} "
                f"recs={len(ranked)} pool={diag_info['pool_size']} "
                f"pool_rank={diag_info['pool_rank']} filt_rank={diag_info['filtered_rank']}{mark}"
            )
            print(f"       user: {message[:90]}")
            print(f"       agent: {response['message'][:90]}")

        if target in ranked and first_hit_turn is None:
            first_hit_turn = turn
            best_rank = ranked.index(target) + 1
            break

        if turn == MAX_TURNS:
            break
        message = customer_reply(
            {"scenario_type": "buying", "intent_card": card},
            response.get("ask_attribute"),
            disclosed,
            False,
        )[0]

    return {
        "target": target,
        "title": str(target_row.get("title", ""))[:60],
        "hit": first_hit_turn is not None,
        "first_hit_turn": first_hit_turn,
        "best_rank": best_rank,
        "reciprocal_rank": 0.0 if best_rank is None else 1.0 / best_rank,
        "pool_hit_turns": pool_hits,
        "filter_kills": filter_kills,
        "avg_pool_size": statistics.fmean(pool_sizes) if pool_sizes else 0.0,
        "avg_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
    }


def summarize(cases: list[dict]) -> dict:
    n = len(cases) or 1
    hits = [c for c in cases if c["hit"]]
    mttc = statistics.fmean(
        c["first_hit_turn"] if c["first_hit_turn"] is not None else MAX_TURNS + 1
        for c in cases
    )
    efficiency = max(0.0, min(1.0, (11.0 - float(mttc)) / 10.0))
    return {
        "cases": len(cases),
        "hit_rate_at_10": round(len(hits) / n, 4),
        "mrr": round(statistics.fmean(c["reciprocal_rank"] for c in cases), 4),
        "mttc": round(mttc, 3),
        "efficiency": round(efficiency, 4),
        "technical_score": round(
            0.50 * (len(hits) / n)
            + 0.30 * statistics.fmean(c["reciprocal_rank"] for c in cases)
            + 0.20 * efficiency,
            4,
        ),
        "avg_pool_size": round(statistics.fmean(c["avg_pool_size"] for c in cases), 1),
        "target_in_pool@200_turns_pct": round(
            100.0
            * sum(c["pool_hit_turns"] for c in cases)
            / max(
                1,
                sum(
                    max(1, MAX_TURNS if not c["hit"] else c["first_hit_turn"])
                    for c in cases
                ),
            ),
            1,
        ),
        "filter_killed_target_turns": sum(c["filter_kills"] for c in cases),
        "avg_latency_ms": round(
            statistics.fmean(c["avg_latency_ms"] for c in cases), 1
        ),
    }


def build_agent(catalog: Path, clarification_cfg: dict) -> Agent:
    strategy = load_strategy()
    strategy["clarification"] = dict(clarification_cfg)
    return Agent(catalog, strategy=strategy)


def print_cases(cases: list[dict]) -> None:
    for c in cases:
        status = (
            f"HIT t{c['first_hit_turn']} rank {c['best_rank']}" if c["hit"] else "MISS"
        )
        print(f"  [{status:<18}] {c['target']}  {c['title']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Oracle product-guessing eval")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--cases", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--strategy", choices=["baseline", "adaptive", "both"], default="both"
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--diag",
        action="store_true",
        help="enable pool diagnostics (extra retrieval per turn)",
    )
    args = parser.parse_args()

    catalog = Path(args.catalog)
    rows = load_catalog(catalog)
    targets = sample_targets(rows, args.cases, args.seed)

    strategies = (
        ["baseline", "adaptive"] if args.strategy == "both" else [args.strategy]
    )
    results: dict[str, tuple[list[dict], dict]] = {}
    for name in strategies:
        cfg = (
            dict(BASELINE_CLARIFICATION)
            if name == "baseline"
            else load_strategy()["clarification"]
        )
        agent = build_agent(catalog, cfg)
        print(f"\n=== strategy: {name} | clarification={cfg} ===")
        cases = []
        for idx, row in enumerate(targets):
            if args.verbose:
                print(
                    f"  case {idx + 1}: {row['parent_asin']} {str(row['title'])[:60]}"
                )
            cases.append(run_case(agent, row, idx, args.verbose, diag=args.diag))
        summary = summarize(cases)
        results[name] = (cases, summary)
        print_cases(cases)
        print(f"\n--- summary [{name}] ---")
        for k, v in summary.items():
            print(f"  {k}: {v}")

    if "baseline" in results and "adaptive" in results:
        b, a = results["baseline"][1], results["adaptive"][1]
        print("\n=== baseline vs adaptive ===")
        for k in b:
            delta = a[k] - b[k] if isinstance(b[k], (int, float)) else ""
            print(
                f"  {k}: {b[k]} -> {a[k]}  ({'' if delta == '' else f'{delta:+.4f}'})"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
