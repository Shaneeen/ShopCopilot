#!/usr/bin/env python3
"""Evaluate 3B's soft signal across weights without changing 3A's defaults.

Runs the official local evaluator, writes machine-readable CSV/JSON plus
Markdown diagnostics, and treats missing ranks as outside the evaluator's
top-10 observation window rather than pretending the full rank is known.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import logging
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluator.local_evaluator import (  # noqa: E402
    TOP_K, catalog_index, coarse_category, evaluate, initial_message,
    load_jsonl, materialize_hidden_fields,
)
from neeshops.config.settings import load_strategy  # noqa: E402
from neeshops.personalization.profile import explain_personalization  # noqa: E402
from scripts.evaluate_ranking_ab import IdentityRanker, _make_agent  # noqa: E402
from neeshops.ranking.heuristic import HeuristicRanker  # noqa: E402

DEFAULT_WEIGHTS = (0.0, 0.025, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40)


def _rank_value(rank: int | None) -> int:
    return rank if rank is not None else TOP_K + 1


def _movement(baseline: int | None, personalized: int | None) -> int:
    """Capped top-k movement; 11 denotes outside the observed top 10."""
    return _rank_value(baseline) - _rank_value(personalized)


def movement_diagnostics(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [_movement(x["baseline_rank"], x["personalized_rank"]) for x in pairs]
    positive = [x for x in deltas if x > 0]
    harmful = [-x for x in deltas if x < 0]
    result: dict[str, Any] = {
        "improved": len(positive), "worsened": len(harmful),
        "unchanged": len(deltas) - len(positive) - len(harmful),
        "mean_positive_movement": round(statistics.fmean(positive), 6) if positive else 0.0,
        "median_positive_movement": statistics.median(positive) if positive else 0.0,
        "mean_harmful_movement": round(statistics.fmean(harmful), 6) if harmful else 0.0,
        "median_harmful_movement": statistics.median(harmful) if harmful else 0.0,
        "largest_improvement": max(positive, default=0),
        "largest_regression": max(harmful, default=0),
    }
    for cutoff in (1, 3, 10):
        eligible = [x for x in pairs if x["baseline_rank"] is not None and x["baseline_rank"] <= cutoff]
        kept = [x for x in eligible if x["personalized_rank"] is not None and x["personalized_rank"] <= cutoff]
        result[f"top_{cutoff}_preservation_rate"] = round(len(kept) / len(eligible), 6) if eligible else None
    return result


def _bootstrap_delta(pairs: list[dict[str, Any]], iterations: int, seed: int = 3) -> list[float] | None:
    if not pairs or iterations <= 0:
        return None
    rng = random.Random(seed)
    values = [x["personalized_rr"] - x["baseline_rr"] for x in pairs]
    means = sorted(statistics.fmean(rng.choice(values) for _ in values) for _ in range(iterations))
    return [round(means[int(0.025 * (iterations - 1))], 6), round(means[int(0.975 * (iterations - 1))], 6)]


def _group_summary(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(items)
    if not rows:
        return {"count": 0, "baseline_mrr": 0.0, "personalized_mrr": 0.0, "mrr_delta": 0.0,
                "baseline_hit_at_10": 0.0, "personalized_hit_at_10": 0.0, "improved": 0, "worsened": 0}
    baseline_mrr = statistics.fmean(x["baseline_rr"] for x in rows)
    personalized_mrr = statistics.fmean(x["personalized_rr"] for x in rows)
    movements = movement_diagnostics(rows)
    return {
        "count": len(rows), "baseline_mrr": round(baseline_mrr, 6),
        "personalized_mrr": round(personalized_mrr, 6), "mrr_delta": round(personalized_mrr - baseline_mrr, 6),
        "baseline_hit_at_10": round(sum(x["baseline_rank"] is not None for x in rows) / len(rows), 6),
        "personalized_hit_at_10": round(sum(x["personalized_rank"] is not None for x in rows) / len(rows), 6),
        "improved": movements["improved"], "worsened": movements["worsened"],
    }


def _richness(count: int) -> str:
    return "0" if count == 0 else "1" if count == 1 else "2-3" if count <= 3 else "4+"


def _baseline_position(rank: int | None) -> str:
    if rank is None:
        return "not retrieved in top 10"
    return "1-3" if rank <= 3 else "4-10"


def _constraint_richness(count: int) -> str:
    return "0-1" if count <= 1 else "2-3" if count <= 3 else "4+"


def _pair_sessions(baseline: dict, personalized: dict, samples: list[dict], products: dict[str, dict], categories: dict[str, list[str]]) -> list[dict[str, Any]]:
    by_sample = {x["sample_id"]: x for x in samples}
    personalized_by_id = {x["sample_id"]: x for x in personalized["sessions"]}
    pairs = []
    for base in baseline["sessions"]:
        sample = by_sample[base["sample_id"]]
        current = personalized_by_id[base["sample_id"]]
        target = str(sample["ground_truth"]["parent_asin"])
        product = products.get(target, {})
        profile = sample.get("user_profile") or {}
        card, behavior = materialize_hidden_fields(sample, products)
        disclosed: set[str] = set()
        message = initial_message({**sample, "intent_card": card, "behavior": behavior}, coarse_category(categories.get(target, [])), disclosed)
        explanation = explain_personalization(product, profile)
        pairs.append({
            "sample_id": base["sample_id"], "scenario_type": base["scenario_type"],
            "user_message": message, "preference_tags": profile.get("preference_tags", []),
            "profile_richness": _richness(len(set(profile.get("preference_tags", [])))),
            "constraint_richness": _constraint_richness(len(card.get("hard_constraints", []))),
            "category": coarse_category(categories.get(target, [])),
            "target_asin": target, "target_title": product.get("title", ""),
            "target_category": coarse_category(categories.get(target, [])),
            "baseline_rank": base["best_rank"], "personalized_rank": current["best_rank"],
            "baseline_rr": base["reciprocal_rank"], "personalized_rr": current["reciprocal_rank"],
            "rank_movement_capped": _movement(base["best_rank"], current["best_rank"]),
            **explanation,
        })
    return pairs


def _breakdowns(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cuts = {
        "profile_richness": lambda x: x["profile_richness"],
        "baseline_position": lambda x: _baseline_position(x["baseline_rank"]),
        "constraint_richness": lambda x: x["constraint_richness"],
        "category": lambda x: x["category"],
    }
    output = []
    for cut, getter in cuts.items():
        grouped: dict[str, list[dict]] = defaultdict(list)
        for pair in pairs:
            grouped[str(getter(pair))].append(pair)
        for group, rows in sorted(grouped.items()):
            # Category cuts with fewer than five examples are too noisy.
            if cut == "category" and len(rows) < 5:
                continue
            output.append({"cut": cut, "group": group, **_group_summary(rows)})
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def _case_markdown(pairs: list[dict[str, Any]], weight: float) -> str:
    def render(title: str, rows: list[dict]) -> list[str]:
        out = [f"## {title}", ""]
        for row in rows:
            out.extend([
                f"### {row['sample_id']}", "",
                f"- Message: {row['user_message']}",
                f"- Preference tags: {', '.join(row['preference_tags']) or 'none'}",
                f"- Target: {row['target_title']} ({row['target_category']})",
                f"- Rank: {row['baseline_rank'] or 'outside top 10'} -> {row['personalized_rank'] or 'outside top 10'} (capped movement {row['rank_movement_capped']:+d})",
                f"- Matched concepts/terms: {', '.join(row['matched_tags']) or 'none'} / {', '.join(row['matched_terms']) or 'none'}",
                f"- Confidence / target score: {row['confidence']:.3f} / {row['score']:.3f}", "",
            ])
        return out
    improved = sorted((x for x in pairs if x["rank_movement_capped"] > 0), key=lambda x: x["rank_movement_capped"], reverse=True)[:10]
    regressed = sorted((x for x in pairs if x["rank_movement_capped"] < 0), key=lambda x: x["rank_movement_capped"])[:10]
    return "\n".join(["# Personalisation case analysis", "", f"Weight: {weight}", "", *render("Top 10 improvements", improved), *render("Top 10 regressions", regressed)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/dev_split.jsonl")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--output-dir", default="evaluation/results")
    parser.add_argument("--weights", nargs="+", type=float, default=DEFAULT_WEIGHTS)
    parser.add_argument("--rerank-limit", type=int, default=50)
    parser.add_argument("--bootstrap-iterations", type=int, default=1000)
    args = parser.parse_args()
    dataset_path, catalog_path = Path(args.dataset), Path(args.catalog)
    if not dataset_path.exists() or not catalog_path.exists():
        print("Dataset or catalog unavailable; no metrics were fabricated.", file=sys.stderr); return 1
    output_dir = Path(args.output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    logging.getLogger("neeshops").setLevel(logging.WARNING)
    samples = load_jsonl(dataset_path)
    catalog_ids, categories, products = catalog_index(catalog_path)
    strategy = copy.deepcopy(load_strategy()); strategy["ranking"]["rerank_limit"] = args.rerank_limit
    print(f"Running retrieval-order baseline for {len(samples)} sessions...")
    baseline = evaluate(_make_agent(IdentityRanker(), catalog_path, strategy), samples, catalog_ids, categories, products)
    summaries, all_pairs = [], {}
    for weight in args.weights:
        print(f"Evaluating personalisation weight {weight:g}...")
        current_strategy = copy.deepcopy(strategy); current_strategy["ranking"]["personalization_weight"] = weight
        result = evaluate(_make_agent(HeuristicRanker(current_strategy), catalog_path, current_strategy), samples, catalog_ids, categories, products)
        pairs = _pair_sessions(baseline, result, samples, products, categories)
        diagnostics = movement_diagnostics(pairs)
        summary = {
            "weight": weight, "sample_count": len(pairs), "baseline_mrr": baseline["mrr"], "personalized_mrr": result["mrr"],
            "mrr_delta": round(result["mrr"] - baseline["mrr"], 6), "baseline_hit_at_10": baseline["hit_rate_at_10"],
            "personalized_hit_at_10": result["hit_rate_at_10"], "baseline_mttc": baseline["mttc"], "personalized_mttc": result["mttc"],
            **diagnostics, "mrr_delta_bootstrap_95_ci": _bootstrap_delta(pairs, args.bootstrap_iterations),
        }
        summaries.append(summary); all_pairs[weight] = pairs
    # Highest MRR is a candidate, with diagnostics visible for stability review.
    recommended = max(summaries, key=lambda x: (x["personalized_mrr"], -x["worsened"], -x["weight"]))
    selected_weight = recommended["weight"]; pairs = all_pairs[selected_weight]
    breakdowns = _breakdowns(pairs)
    flat_summaries = [{**x, "mrr_delta_bootstrap_95_ci": json.dumps(x["mrr_delta_bootstrap_95_ci"])} for x in summaries]
    _write_csv(output_dir / "personalization_weight_sweep.csv", flat_summaries)
    _write_csv(output_dir / "personalization_breakdowns.csv", breakdowns)
    (output_dir / "personalization_case_analysis.md").write_text(_case_markdown(pairs, selected_weight), encoding="utf-8")
    payload = {"dataset": str(dataset_path), "rank_observation_note": "Ranks beyond top 10 are unavailable; movement uses 11 as a capped sentinel.",
               "selection_note": "Highest dev MRR candidate; review preservation/regret before integration.", "recommended_candidate_weight": selected_weight,
               "weight_sweep": summaries, "selected_weight_breakdowns": breakdowns, "selected_weight_sessions": pairs}
    (output_dir / "personalization_evaluation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = ["# Personalisation weight sweep", "", "Ranks beyond top 10 are unavailable and are represented as 11 only for capped movement diagnostics.", "",
             "| Weight | MRR | Delta | Hit@10 | MTTC | Improved | Worsened | Unchanged | Top-3 preserve |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in summaries:
        lines.append(f"| {x['weight']:g} | {x['personalized_mrr']:.6f} | {x['mrr_delta']:+.6f} | {x['personalized_hit_at_10']:.6f} | {x['personalized_mttc']:.6f} | {x['improved']} | {x['worsened']} | {x['unchanged']} | {x['top_3_preservation_rate']} |")
    lines.extend(["", f"Recommended candidate weight: **{selected_weight:g}**. This is a dev-set candidate, not an automatic production change."])
    (output_dir / "personalization_weight_sweep.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"recommended_candidate_weight": selected_weight, **recommended}, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
