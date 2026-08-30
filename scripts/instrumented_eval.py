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


def build_agent(catalog_path: Path) -> NeeShopsAgent:
    """The same wiring starter.Agent does, exposing the full NeeShopsAgent."""
    bm25 = BM25Retriever(catalog_path=catalog_path)
    retriever = HybridRetriever(bm25=bm25)
    lookup = load_catalog_lookup(catalog_path)
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
        recs = response.get("recommendations") or []
        scores = []
        for r in recs:
            try:
                scores.append(
                    float(r.get("score", 0.0))
                    if isinstance(r, dict)
                    else float(getattr(r, "score", 0.0))
                )
            except Exception:
                scores.append(0.0)
        margin = (scores[0] - scores[1]) if len(scores) >= 2 else None
        # Finer relevance margin from ranker diagnostics (violations compress ordering_score to same value)
        relevance_margin = None
        try:
            diags = getattr(agent.ranker, "last_diagnostics", {}) or {}
            # also fallback ranker
            if not diags and hasattr(agent, "_fallback_ranker"):
                diags = getattr(agent._fallback_ranker, "last_diagnostics", {}) or {}
            rec_asins = [
                r.get("parent_asin")
                if isinstance(r, dict)
                else getattr(r, "parent_asin", None)
                for r in recs[:2]
            ]
            if len(rec_asins) >= 2 and rec_asins[0] in diags and rec_asins[1] in diags:
                relevance_margin = float(diags[rec_asins[0]].relevance_score) - float(
                    diags[rec_asins[1]].relevance_score
                )
        except Exception:
            relevance_margin = None
        rank = ranked.index(target) + 1 if target in ranked else None
        if target in ranked:
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
                "pool_rank": pool_rank,
                "retrieval_rank": retrieval_rank,
                "and_set_size": response_diag.get("and_set_size"),
                "pool_size": response_diag.get("pool_size"),
                "over_generality": response_diag.get("over_generality"),
                "target_rank": rank if target in ranked else None,
                "llm_fallback": response_diag.get("llm_fallback"),
                "margin": margin,
                "relevance_margin": relevance_margin,
                "ranked_scores": scores[:10] if scores else [],
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

    return {
        "sample_id": sample["sample_id"],
        "scenario_type": sample["scenario_type"],
        "hit": hit,
        "first_hit_turn": hit_turn,
        "best_rank": best_rank,
        "reciprocal_rank": 0.0 if best_rank is None else 1.0 / best_rank,
        "pool_hit_turns": pool_hit_turns,
        "retrieval_hit_turns": retrieval_hit_turns,
        "turns_run": turns_run,
        "questions_asked": questions_asked,
        "miss_type": miss_type,
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
        }
    )
    return panel


def profile_last_question(sessions: list[dict], rerank_floor: int = 40) -> dict:
    rows = []
    for s in sessions:
        if s["hit"]:
            continue
        turns = s.get("turns") or []
        last_q_idx = -1
        for i, t in enumerate(turns):
            if t.get("asked"):
                last_q_idx = i
        if last_q_idx == -1:
            rows.append(
                {
                    "sample_id": s["sample_id"],
                    "scenario_type": s["scenario_type"],
                    "miss_type": s["miss_type"],
                    "has_last_question": False,
                }
            )
            continue
        if last_q_idx + 1 >= len(turns):
            rows.append(
                {
                    "sample_id": s["sample_id"],
                    "scenario_type": s["scenario_type"],
                    "miss_type": s["miss_type"],
                    "has_last_question": True,
                    "last_q_turn": turns[last_q_idx]["turn"],
                    "last_q_attr": turns[last_q_idx].get("asked"),
                    "last_q_gate": turns[last_q_idx].get("gate"),
                    "before_and": turns[last_q_idx].get("and_set_size"),
                    "after_and": None,
                    "before_pool": turns[last_q_idx].get("pool_size"),
                    "after_pool": None,
                    "before_margin": turns[last_q_idx].get("margin"),
                    "after_margin": None,
                    "before_rel_margin": turns[last_q_idx].get("relevance_margin"),
                    "after_rel_margin": None,
                    "pct_reduction_and": None,
                    "pct_reduction_pool": None,
                    "margin_delta": None,
                    "rel_margin_delta": None,
                    "late_phase": None,
                    "measurable": False,
                }
            )
            continue
        before = turns[last_q_idx]
        after = turns[last_q_idx + 1]
        before_and = before.get("and_set_size")
        after_and = after.get("and_set_size")
        before_pool = before.get("pool_size")
        after_pool = after.get("pool_size")
        before_margin = before.get("margin")
        after_margin = after.get("margin")
        before_rel = before.get("relevance_margin")
        after_rel = after.get("relevance_margin")
        pct_and = None
        if (
            isinstance(before_and, (int, float))
            and isinstance(after_and, (int, float))
            and before_and
            and before_and > 0
        ):
            pct_and = (before_and - after_and) / before_and * 100.0
        pct_pool = None
        if (
            isinstance(before_pool, (int, float))
            and isinstance(after_pool, (int, float))
            and before_pool
            and before_pool > 0
        ):
            pct_pool = (before_pool - after_pool) / before_pool * 100.0
        pct = pct_and if pct_and is not None else pct_pool
        delta = None
        if isinstance(before_margin, (int, float)) and isinstance(
            after_margin, (int, float)
        ):
            delta = after_margin - before_margin
        rel_delta = None
        if isinstance(before_rel, (int, float)) and isinstance(after_rel, (int, float)):
            rel_delta = after_rel - before_rel
        late = None
        cand_before = (
            before_and if isinstance(before_and, (int, float)) else before_pool
        )
        if isinstance(cand_before, (int, float)):
            late = cand_before <= rerank_floor
        rows.append(
            {
                "sample_id": s["sample_id"],
                "scenario_type": s["scenario_type"],
                "miss_type": s["miss_type"],
                "has_last_question": True,
                "last_q_turn": before["turn"],
                "last_q_attr": before.get("asked"),
                "last_q_gate": before.get("gate"),
                "before_and": before_and,
                "after_and": after_and,
                "before_pool": before_pool,
                "after_pool": after_pool,
                "before_margin": before_margin,
                "after_margin": after_margin,
                "before_rel_margin": before_rel,
                "after_rel_margin": after_rel,
                "pct_reduction_and": pct_and,
                "pct_reduction_pool": pct_pool,
                "pct_reduction": pct,
                "margin_delta": delta,
                "rel_margin_delta": rel_delta,
                "late_phase": late,
                "measurable": pct is not None and delta is not None,
                "measurable_rel": pct is not None and rel_delta is not None,
            }
        )
    measurable = [r for r in rows if r.get("measurable")]
    measurable_rel = [r for r in rows if r.get("measurable_rel")]
    large_collapse_threshold = 30.0
    flat_margin_threshold = 0.01
    rel_flat_threshold = 0.02

    def is_large_collapse(r):
        return (
            r["pct_reduction"] is not None
            and r["pct_reduction"] >= large_collapse_threshold
        )

    def is_flat_margin(r):
        return (
            r["margin_delta"] is not None and r["margin_delta"] <= flat_margin_threshold
        )

    def is_flat_rel(r):
        return (
            r["rel_margin_delta"] is not None
            and r["rel_margin_delta"] <= rel_flat_threshold
        )

    pattern = [r for r in measurable if is_large_collapse(r) and is_flat_margin(r)]
    pattern_rel = [r for r in measurable_rel if is_large_collapse(r) and is_flat_rel(r)]
    # late-phase subset
    late_measurable = [r for r in measurable if r.get("late_phase")]
    late_measurable_rel = [r for r in measurable_rel if r.get("late_phase")]
    late_pattern = [
        r for r in late_measurable if is_large_collapse(r) and is_flat_margin(r)
    ]
    late_pattern_rel = [
        r for r in late_measurable_rel if is_large_collapse(r) and is_flat_rel(r)
    ]
    # looser thresholds for sensitivity
    pattern_loose = [
        r
        for r in measurable
        if r["pct_reduction"] is not None
        and r["pct_reduction"] >= 20.0
        and r["margin_delta"] is not None
        and r["margin_delta"] <= 0.02
    ]
    pattern_loose_rel = [
        r
        for r in measurable_rel
        if r["pct_reduction"] is not None
        and r["pct_reduction"] >= 20.0
        and r["rel_margin_delta"] is not None
        and r["rel_margin_delta"] <= 0.02
    ]
    # Also compute strictly negative margin
    pattern_negative = [
        r
        for r in measurable
        if is_large_collapse(r)
        and r["margin_delta"] is not None
        and r["margin_delta"] <= 0
    ]
    pattern_negative_rel = [
        r
        for r in measurable_rel
        if is_large_collapse(r)
        and r["rel_margin_delta"] is not None
        and r["rel_margin_delta"] <= 0
    ]
    summary = {
        "total_misses": sum(1 for s in sessions if not s["hit"]),
        "misses_with_last_q": sum(1 for r in rows if r.get("has_last_question")),
        "measurable": len(measurable),
        "measurable_rel": len(measurable_rel),
        "large_set_collapse_ge30": sum(1 for r in measurable if is_large_collapse(r)),
        "flat_margin_le0_01": sum(1 for r in measurable if is_flat_margin(r)),
        "pattern_large_collapse_and_flat_margin_ge30_le0_01": len(pattern),
        "pattern_fraction": round(len(pattern) / len(measurable), 4)
        if measurable
        else 0.0,
        "pattern_fraction_of_all_misses": round(
            len(pattern) / max(1, sum(1 for s in sessions if not s["hit"])), 4
        ),
        "pattern_rel_ge30_le0_02": len(pattern_rel),
        "pattern_rel_fraction": round(len(pattern_rel) / len(measurable_rel), 4)
        if measurable_rel
        else 0.0,
        "pattern_negative": len(pattern_negative),
        "pattern_negative_rel": len(pattern_negative_rel),
        "late_phase_measurable": len(late_measurable),
        "late_phase_measurable_rel": len(late_measurable_rel),
        "late_pattern": len(late_pattern),
        "late_pattern_rel": len(late_pattern_rel),
        "late_pattern_fraction": round(len(late_pattern) / len(late_measurable), 4)
        if late_measurable
        else None,
        "late_pattern_rel_fraction": round(
            len(late_pattern_rel) / len(late_measurable_rel), 4
        )
        if late_measurable_rel
        else None,
        "loose_pattern_ge20_le0_02": len(pattern_loose),
        "loose_fraction": round(len(pattern_loose) / len(measurable), 4)
        if measurable
        else 0.0,
        "loose_pattern_rel": len(pattern_loose_rel),
        "loose_rel_fraction": round(len(pattern_loose_rel) / len(measurable_rel), 4)
        if measurable_rel
        else 0.0,
        "thresholds": {
            "large_collapse_pct": large_collapse_threshold,
            "flat_margin_delta": flat_margin_threshold,
            "rel_flat_margin_delta": rel_flat_threshold,
            "rerank_floor": rerank_floor,
        },
        "rows": rows,
    }
    return summary


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
    agent = build_agent(Path(args.catalog))

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

    gate = profile_last_question(sessions)
    panel["gate_last_question_profile"] = {k: v for k, v in gate.items() if k != "rows"}
    print("=== GATE last-question profile (misses only) ===")
    print(json.dumps({k: v for k, v in gate.items() if k != "rows"}, indent=2))
    for r in gate["rows"]:
        if r.get("measurable"):
            pct = r["pct_reduction"]
            pct_str = f"{pct:.1f}%" if isinstance(pct, float) else "NA"
            print(
                f"{r['sample_id']:12} {r['scenario_type']:15} q={r['last_q_attr']:10} gate={str(r['last_q_gate']):14} before_and={str(r['before_and']):6} after_and={str(r['after_and']):6} pct={pct_str:>7} margin {r['before_margin']!s:>6}->{r['after_margin']!s:>6} d={r['margin_delta']!s:>6} rel {r['before_rel_margin']!s:>7}->{r['after_rel_margin']!s:>7} d_rel={str(round(r['rel_margin_delta'], 4)) if isinstance(r['rel_margin_delta'], float) else r['rel_margin_delta']:>7} late={r['late_phase']}"
            )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"panel": panel, "sessions": sessions, "gate_profile": gate}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(panel, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
