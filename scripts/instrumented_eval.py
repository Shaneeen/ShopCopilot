#!/usr/bin/env python3
"""Instrumented evaluation wrapper — the P0 measurement panel.

Runs the OFFICIAL evaluator protocol (evaluator/local_evaluator.py is frozen
and never modified) by importing its primitives — the same read-only-import
pattern scripts/run_oracle_eval.py established — against a NeeShopsAgent so
the full internal response (including `diagnostics`) is visible. Adds:

- per-turn pool diagnostics: where the target stood in the 200-candidate
  pipeline (raw retrieval rank → post-guarantee/post-filter pool rank)
- latency p50/p95 per respond()
- miss decomposition per session:
    pool | rank | extraction | insufficient_constraints |
    override_not_yet_delivered
- aggregate panel: target_in_pool_at_200, filter_kill_rate, avg_questions,
  hit@1/3/5/10, MRR, MTTC, efficiency, TechnicalScore, LLM fallback rate,
  over-generality events, final AND-set size — plus per-scenario metrics.

    python scripts/instrumented_eval.py                 # public 200
    python scripts/instrumented_eval.py --limit 50      # quick panel
"""

from __future__ import annotations

import argparse
import json
import os
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
    catalog_index,
    coarse_category,
    customer_reply,
    initial_message,
    load_jsonl,
    materialize_hidden_fields,
    metric_summary,
    normalize_recommendations,
)
from neeshops.agent import NeeShopsAgent  # noqa: E402
from neeshops.retrieval.bm25 import BM25Retriever  # noqa: E402
from neeshops.retrieval.hybrid import HybridRetriever  # noqa: E402
from neeshops.retrieval.token_index import index_tokenize  # noqa: E402
from neeshops.utils.catalog import load_catalog_lookup  # noqa: E402

MISS_TYPES = (
    "pool",
    "rank",
    "extraction",
    "insufficient_constraints",
    "override_not_yet_delivered",
)

# Binary miss taxonomy for the rank-vs-pool hypothesis (docs/V3.md §6.2.1):
# a "pool" miss means the target NEVER entered the 200-candidate pool this
# session; a "rank" miss means it was in the pool but never surfaced in the
# top-10. rank_fix_ceiling = current Hit + rank_misses/N — the Hit@10 the
# current pool could reach with a perfect ranker (pool misses untouched).
TAXONOMY = ("pool", "rank")


def _miss_taxonomy(session: dict) -> str:
    """Map the detailed miss_type to the binary pool/rank taxonomy."""
    if session["pool_hit_turns"] == 0:
        return "pool"
    return "rank"


def build_agent(
    catalog_path: Path, catalog_lookup: dict | None = None
) -> NeeShopsAgent:
    """The same wiring starter.Agent does, exposing the full NeeShopsAgent."""
    bm25 = BM25Retriever(catalog_path=catalog_path)
    retriever = HybridRetriever(bm25=bm25)
    lookup = (
        catalog_lookup
        if catalog_lookup is not None
        else load_catalog_lookup(catalog_path)
    )
    return NeeShopsAgent(
        retriever=retriever, catalog_lookup=lookup, catalog_path=catalog_path
    )


def _extraction_miss(agent: NeeShopsAgent, session_id: str, target: str) -> bool:
    """The target's own text does not contain the stated constraint tokens
    → paraphrase or extraction bug (→ forensics loop)."""
    if agent.token_index is None:
        return False
    doc_tokens = agent.token_index.doc_tokens(target)
    if doc_tokens is None:
        return False
    state = agent.state_manager.get(session_id)
    stated: set[str] = set()
    for field, value in state.constraints.items():
        if field in ("budget", "other") or value is None or value == "NO_PREFERENCE":
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            continue
        if isinstance(value, str) and value.strip():
            stated.update(index_tokenize(value))
    return bool(stated - doc_tokens)


def _insufficient_constraints(agent: NeeShopsAgent, session_id: str) -> bool:
    state = agent.state_manager.get(session_id)
    informative = sum(1 for t in state.history if t.informative)
    active = sum(
        1
        for field, value in state.constraints.items()
        if field not in ("budget", "other")
        and value is not None
        and value != "NO_PREFERENCE"
        and (not isinstance(value, str) or value.strip())
    )
    return informative < 2 or active < 1


def run_session(
    agent: NeeShopsAgent,
    sample: dict,
    catalog_ids: set[str],
    categories: dict[str, list[str]],
    products: dict[str, dict],
) -> dict:
    session_id = f"public_{sample['sample_id']}"
    agent.reset(session_id, sample["user_profile"])
    target = str(sample["ground_truth"]["parent_asin"])
    intent_card, behavior = materialize_hidden_fields(sample, products)
    effective_sample = {**sample, "intent_card": intent_card, "behavior": behavior}
    disclosed: set[str] = set()
    boundary_used = False
    override_applied = sample["scenario_type"] != "intent_override"
    user_message = initial_message(
        effective_sample, coarse_category(categories.get(target, [])), disclosed
    )

    hit_turn: int | None = None
    best_rank: int | None = None
    pool_hit_turns = 0
    turns_run = 0
    retrieval_hit_turns = 0
    questions_asked = 0
    latencies: list[float] = []
    turn_records: list[dict] = []
    pre_override_target_rank: int | None = None
    final_diag: dict = {}

    for turn in range(1, MAX_TURNS + 1):
        start = time.perf_counter()
        response = agent.respond(session_id, user_message, turn, TOP_K)
        latencies.append((time.perf_counter() - start) * 1000)

        # The pool this turn actually ranked (no recomputation).
        pool = agent.last_candidates
        hybrid = agent.last_hybrid_pool
        pool_rank = next(
            (i + 1 for i, c in enumerate(pool) if c.parent_asin == target), None
        )
        retrieval_rank = next(
            (i + 1 for i, c in enumerate(hybrid) if c.parent_asin == target), None
        )
        response_diag = response.get("diagnostics") or {}
        turns_run += 1
        if pool_rank is not None:
            pool_hit_turns += 1
        if retrieval_rank is not None:
            retrieval_hit_turns += 1
        if response.get("ask_attribute"):
            questions_asked += 1
        ranked = normalize_recommendations(response.get("recommendations"), catalog_ids)
        rank = None
        if target in ranked:
            rank = ranked.index(target) + 1
            if override_applied:
                best_rank = rank
                hit_turn = turn
            elif pre_override_target_rank is None:
                pre_override_target_rank = rank
        turn_records.append(
            {
                "turn": turn,
                "asked": response.get("ask_attribute"),
                "gate": response_diag.get("decision_gate"),
                "route": response_diag.get("route")
                or agent.state_manager.get(session_id).route,
                "pool_rank": pool_rank,
                "retrieval_rank": retrieval_rank,
                "and_set_size": response_diag.get("and_set_size"),
                "over_generality": response_diag.get("over_generality"),
                "target_rank": rank,
                "llm_fallback": response_diag.get("llm_fallback"),
            }
        )
        final_diag = dict(response_diag)

        if hit_turn is not None:
            break
        if turn == MAX_TURNS:
            break
        override = effective_sample.get("behavior", {}).get("override") or {}
        if not override_applied and turn + 1 == int(override.get("turn", 3)):
            override_applied = True
            new_value = str(override.get("new_value", ""))
            if new_value:
                disclosed.add(new_value)
            user_message = str(
                override.get(
                    "message", "Actually, please ignore my earlier preference."
                )
            )
        else:
            user_message, boundary_used = customer_reply(
                effective_sample,
                response.get("ask_attribute"),
                disclosed,
                boundary_used,
            )

    hit = hit_turn is not None
    miss_type = None
    if not hit:
        if pool_hit_turns == 0:
            miss_type = "pool"
        elif pre_override_target_rank is not None:
            miss_type = "override_not_yet_delivered"
        elif _extraction_miss(agent, session_id, target):
            miss_type = "extraction"
        elif _insufficient_constraints(agent, session_id):
            miss_type = "insufficient_constraints"
        else:
            miss_type = "rank"
    miss_taxonomy = None
    if not hit:
        miss_taxonomy = "pool" if pool_hit_turns == 0 else "rank"

    return {
        "sample_id": sample["sample_id"],
        "scenario_type": sample["scenario_type"],
        "hit": hit,
        "miss_taxonomy": _miss_taxonomy({"pool_hit_turns": pool_hit_turns})
        if not hit
        else None,
        "first_hit_turn": hit_turn,
        "best_rank": best_rank,
        "reciprocal_rank": 0.0 if best_rank is None else 1.0 / best_rank,
        "pool_hit_turns": pool_hit_turns,
        "retrieval_hit_turns": retrieval_hit_turns,
        "turns_run": turns_run,
        "questions_asked": questions_asked,
        "miss_type": miss_type,
        "miss_taxonomy": miss_taxonomy,
        "final_and_set_size": final_diag.get("and_set_size"),
        "latency_ms": statistics.fmean(latencies) if latencies else 0.0,
        "turns": turn_records,
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct / 100.0 * (len(ordered) - 1))))
    return ordered[idx]


def summarize_panel(sessions: list[dict]) -> dict:
    n = len(sessions) or 1
    turns_total = sum(s["turns_run"] for s in sessions) or 1
    panel = metric_summary(sessions)
    efficiency = max(0.0, min(1.0, (11.0 - float(panel["mttc"] or 11.0)) / 10.0))
    hit_at = {
        f"hit_at_{k}": sum(
            1 for s in sessions if s["best_rank"] is not None and s["best_rank"] <= k
        )
        / n
        for k in (1, 3, 5, 10)
    }
    miss_counts: dict[str, int] = {name: 0 for name in MISS_TYPES}
    for s in sessions:
        if s["miss_type"] is not None:
            miss_counts[s["miss_type"]] += 1
    taxonomy_counts: dict[str, int] = {name: 0 for name in TAXONOMY}
    per_route_taxonomy: dict[str, dict[str, int]] = {}
    for s in sessions:
        if s.get("miss_taxonomy") is not None:
            taxonomy_counts[s["miss_taxonomy"]] += 1
            route = s["scenario_type"]
            bucket = per_route_taxonomy.setdefault(route, {"pool": 0, "rank": 0})
            bucket[s["miss_taxonomy"]] += 1
    rank_fix_ceiling = float(panel["hit_rate_at_10"]) + taxonomy_counts["rank"] / n
    and_sizes = [
        s["final_and_set_size"]
        for s in sessions
        if isinstance(s["final_and_set_size"], (int, float))
    ]
    panel.update(
        {
            "efficiency": round(efficiency, 6),
            "recommended_technical_score": round(
                0.50 * panel["hit_rate_at_10"]
                + 0.30 * panel["mrr"]
                + 0.20 * efficiency,
                6,
            ),
            **{k: round(v, 6) for k, v in hit_at.items()},
            "target_in_pool_at_200": round(
                100.0 * sum(s["pool_hit_turns"] for s in sessions) / turns_total, 2
            ),
            "target_in_retrieval_at_200": round(
                100.0 * sum(s["retrieval_hit_turns"] for s in sessions) / turns_total, 2
            ),
            "filter_kill_rate": round(
                (
                    sum(s["retrieval_hit_turns"] for s in sessions)
                    - sum(s["pool_hit_turns"] for s in sessions)
                )
                / turns_total,
                4,
            ),
            "avg_questions": round(sum(s["questions_asked"] for s in sessions) / n, 3),
            "avg_final_and_set_size": round(statistics.fmean(and_sizes), 1)
            if and_sizes
            else None,
            "over_generality_sessions": sum(
                1 for s in sessions if any(t["over_generality"] for t in s["turns"])
            ),
            "llm_fallback_turns": sum(
                1 for s in sessions for t in s["turns"] if t["llm_fallback"]
            ),
            "p50_latency_ms": round(
                percentile([s["latency_ms"] for s in sessions], 50), 1
            ),
            "p95_latency_ms": round(
                percentile([s["latency_ms"] for s in sessions], 95), 1
            ),
            "miss_decomposition": miss_counts,
            "miss_taxonomy": taxonomy_counts,
            "miss_taxonomy_pool_vs_rank": taxonomy_counts,
            "miss_taxonomy_per_route": per_route_taxonomy,
            "rank_fix_ceiling": round(rank_fix_ceiling, 6),
        }
    )
    return panel


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Instrumented public-set evaluation panel"
    )
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument(
        "--output", default="evaluation/results/instrumented_results.json"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="only run the first N samples"
    )
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    if args.limit:
        samples = samples[: args.limit]
    catalog_ids, categories, products = catalog_index(args.catalog)
    agent = build_agent(Path(args.catalog), catalog_lookup=products)

    sessions = []
    for sample in samples:
        sessions.append(run_session(agent, sample, catalog_ids, categories, products))

    panel = summarize_panel(sessions)
    grouped: dict[str, list[dict]] = {}
    for s in sessions:
        grouped.setdefault(s["scenario_type"], []).append(s)
    panel["scenario_metrics"] = {
        name: summarize_panel(group) for name, group in sorted(grouped.items())
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"panel": panel, "sessions": sessions}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(panel, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
