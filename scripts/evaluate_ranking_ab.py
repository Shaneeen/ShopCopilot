#!/usr/bin/env python3
"""P3-D5 — A/B evaluate HeuristicRanker against an identity/pass-through
ranker on the same dataset, and report the MRR delta.

This is the NeeShops-side half of the ranking evaluation Person 3A and
Person 3B both own (see docs/neeshops/TEAM_WORKSTREAMS.md). Rather than
re-parsing an exported top-10 JSON (which has no ground-truth field to
compute MRR against), this script runs the real official evaluator
(`evaluator/local_evaluator.py`) twice against the same samples/catalog:

  * "baseline" — retrieval order only (IdentityRanker: no reranking,
    no personalization boost). This is the *retrieval_baseline_top_10*
    equivalent.
  * "ranked" — the real `HeuristicRanker` (personalization blended in).
    This is the *ranked_top_10* equivalent.

Both runs share one retrieval pipeline/config, so any MRR difference is
attributable only to the ranking stage.

    python scripts/evaluate_ranking_ab.py
    python scripts/evaluate_ranking_ab.py --dataset data/public_set.jsonl
    python scripts/evaluate_ranking_ab.py --rerank-limit 50 --personalization-weight 0.15

Prints baseline_mrr / ranked_mrr / mrr_delta, a per-scenario breakdown, and
saves the full result (including a per-sample_id table so specific cases
can be cross-checked against Person 3A's own numbers) under
artifacts/experiments/.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from neeshops.agent import NeeShopsAgent
from neeshops.config.settings import load_strategy
from neeshops.models.recommendation import Recommendation
from neeshops.models.session import ConversationState
from neeshops.ranking.base import Ranker
from neeshops.ranking.heuristic import HeuristicRanker
from neeshops.retrieval.base import Candidate
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.hybrid import HybridRetriever
from neeshops.utils.catalog import load_catalog_lookup

ARTIFACTS_DIR = Path("artifacts/experiments")


class IdentityRanker(Ranker):
    """Pass-through ranker: keeps retrieval order, applies no personalization
    boost. This is the "no-reranking" A/B arm — retrieval already returns
    candidates sorted best-first (see neeshops/retrieval/candidate_merge.py),
    so this ranker only truncates to top_k and wraps each candidate as a
    Recommendation.
    """

    name = "identity"

    def rank(
        self,
        candidates: list[Candidate],
        catalog_lookup: dict[str, dict[str, Any]],
        state: ConversationState,
        top_k: int,
    ) -> list[Recommendation]:
        return [
            Recommendation(
                parent_asin=c.parent_asin,
                score=c.score,
                reason="Retrieval order (no reranking)",
                source=c.source,
            )
            for c in candidates[:top_k]
        ]


def _make_agent(ranker: Ranker, catalog_path: Path, strategy: dict[str, Any]) -> NeeShopsAgent:
    bm25 = BM25Retriever(catalog_path=catalog_path)
    retriever = HybridRetriever(bm25=bm25, strategy=strategy)
    catalog_lookup = load_catalog_lookup(catalog_path)
    return NeeShopsAgent(
        retriever=retriever, ranker=ranker, catalog_lookup=catalog_lookup, strategy=strategy
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="data/dev_split.jsonl")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--personalization-weight", type=float, default=0.15)
    parser.add_argument("--rerank-limit", type=int, default=50)
    parser.add_argument("--label", default="ranking_ab")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    dataset_path = Path(args.dataset)
    if not catalog_path.exists():
        print(f"Catalog not found at {catalog_path}. See data/README.md.")
        return 1
    if not dataset_path.exists():
        print(f"{dataset_path} not found — run scripts/create_dev_split.py first.")
        return 1

    strategy = copy.deepcopy(load_strategy())
    strategy["ranking"]["personalization_weight"] = args.personalization_weight
    strategy["ranking"]["rerank_limit"] = args.rerank_limit

    samples = load_jsonl(dataset_path)
    catalog_ids, categories, products = catalog_index(catalog_path)

    print(f"Evaluating {len(samples)} sessions from {dataset_path} ...")
    print(f"  ranker config: personalization_weight={args.personalization_weight}, rerank_limit={args.rerank_limit}\n")

    baseline_agent = _make_agent(IdentityRanker(), catalog_path, strategy)
    baseline_result = evaluate(baseline_agent, samples, catalog_ids, categories, products)

    ranked_agent = _make_agent(HeuristicRanker(strategy=strategy), catalog_path, strategy)
    ranked_result = evaluate(ranked_agent, samples, catalog_ids, categories, products)

    baseline_mrr = baseline_result["mrr"]
    ranked_mrr = ranked_result["mrr"]
    mrr_delta = round(ranked_mrr - baseline_mrr, 6)

    print(f"  baseline_mrr (identity/no-reranking): {baseline_mrr}")
    print(f"  ranked_mrr   (HeuristicRanker):        {ranked_mrr}")
    print(f"  mrr_delta    (ranked - baseline):      {mrr_delta}\n")

    print(f"  baseline hit_rate_at_10: {baseline_result['hit_rate_at_10']}")
    print(f"  ranked   hit_rate_at_10: {ranked_result['hit_rate_at_10']}\n")

    print("  Per-scenario MRR (baseline -> ranked):")
    for scenario in sorted(baseline_result["scenario_metrics"]):
        b = baseline_result["scenario_metrics"][scenario]["mrr"]
        r = ranked_result["scenario_metrics"].get(scenario, {}).get("mrr")
        print(f"    {scenario:20s} {b} -> {r}")

    baseline_by_id = {s["sample_id"]: s for s in baseline_result["sessions"]}
    ranked_by_id = {s["sample_id"]: s for s in ranked_result["sessions"]}
    per_sample = [
        {
            "sample_id": sample_id,
            "scenario_type": baseline_by_id[sample_id]["scenario_type"],
            "baseline_best_rank": baseline_by_id[sample_id]["best_rank"],
            "ranked_best_rank": ranked_by_id[sample_id]["best_rank"],
            "baseline_reciprocal_rank": baseline_by_id[sample_id]["reciprocal_rank"],
            "ranked_reciprocal_rank": ranked_by_id[sample_id]["reciprocal_rank"],
        }
        for sample_id in baseline_by_id
    ]

    summary = {
        "dataset": str(dataset_path),
        "catalog": str(catalog_path),
        "ranker_configuration": {
            "personalization_weight": args.personalization_weight,
            "rerank_limit": args.rerank_limit,
        },
        "sample_count": baseline_result["sample_count"],
        "baseline_mrr": baseline_mrr,
        "ranked_mrr": ranked_mrr,
        "mrr_delta": mrr_delta,
        "baseline_hit_rate_at_10": baseline_result["hit_rate_at_10"],
        "ranked_hit_rate_at_10": ranked_result["hit_rate_at_10"],
        "baseline_scenario_metrics": baseline_result["scenario_metrics"],
        "ranked_scenario_metrics": ranked_result["scenario_metrics"],
        "per_sample": per_sample,
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / f"{args.label}_{int(time.time())}.json"
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved full A/B result to {out_path}")
    print(
        "Record the accepted numbers in docs/neeshops/EXPERIMENTS.md "
        "(see 3B_PERSONALIZATION_EVAL.md, P3-D5)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
