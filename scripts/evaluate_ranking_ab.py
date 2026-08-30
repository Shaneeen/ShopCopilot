#!/usr/bin/env python3
"""P3-D5: evaluate retrieval, current ranking, and personalisation separately.

The important A/B comparison for Person 3B holds the current production
``ConstraintAwareRanker`` constant and changes only its personalisation
feature. A retrieval-order identity arm is also reported so Person 3A can
measure the complete ranking-stage delta without conflating it with the
personalisation delta.

    .venv/bin/python scripts/evaluate_ranking_ab.py
    .venv/bin/python scripts/evaluate_ranking_ab.py --dataset data/public_set.jsonl
    .venv/bin/python scripts/evaluate_ranking_ab.py --personalization-weight 0.03

The full, per-session result is written under ``artifacts/experiments``.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
import time
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
from typing import Any

# V2 uses set-backed candidate intersections. Lock Python's hash seed before
# importing the pipeline so repeated evaluation processes produce comparable
# ordering. This block runs only for the CLI, never when tests import helpers.
if __name__ == "__main__" and os.environ.get("PYTHONHASHSEED") != "0":
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = "0"
    os.execve(sys.executable, [sys.executable, *sys.argv], environment)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from neeshops.agent import NeeShopsAgent
from neeshops.config.settings import load_strategy
from neeshops.models.recommendation import Recommendation
from neeshops.models.session import ConversationState
from neeshops.ranking.base import Ranker
from neeshops.ranking.deterministic import ConstraintAwareRanker
from neeshops.retrieval.base import Candidate
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.hybrid import HybridRetriever
from neeshops.utils.catalog import load_catalog_lookup

ARTIFACTS_DIR = Path("artifacts/experiments")


class IdentityRanker(Ranker):
    """Pass through retrieval order without reranking or personalisation."""

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
                parent_asin=candidate.parent_asin,
                score=candidate.score,
                reason="Retrieval order (no reranking)",
                source=candidate.source,
            )
            for candidate in candidates[:top_k]
        ]


def strategy_with_personalization(
    strategy: dict[str, Any], weight: float, rerank_limit: int
) -> dict[str, Any]:
    """Return a copy configured for the active deterministic ranker.

    ``ranking.personalization_weight`` is retained for the legacy heuristic
    and LLM paths. V2's deployed ranker reads the nested deterministic
    weight, so evaluation tooling keeps both keys in sync.
    """
    if weight < 0:
        raise ValueError("personalization weight must be non-negative")
    configured = copy.deepcopy(strategy)
    ranking = configured["ranking"]
    deterministic = ranking["deterministic"]
    ranking["personalization_weight"] = weight
    ranking["rerank_limit"] = rerank_limit
    deterministic["rerank_limit"] = rerank_limit
    deterministic["weights"]["personalization"] = weight
    deterministic["features_enabled"]["personalization"] = weight > 0
    # P3-D5 is an offline deterministic comparison. Optional live calls
    # would add an unrelated variable to the personalisation A/B.
    configured["feature_flags"]["enable_llm_reranker"] = False
    return configured


def _make_agent(
    ranker: Ranker,
    catalog_path: Path,
    strategy: dict[str, Any],
) -> NeeShopsAgent:
    bm25 = BM25Retriever(catalog_path=catalog_path)
    retriever = HybridRetriever(bm25=bm25, strategy=strategy)
    catalog_lookup = load_catalog_lookup(catalog_path)
    return NeeShopsAgent(
        retriever=retriever,
        ranker=ranker,
        catalog_lookup=catalog_lookup,
        strategy=strategy,
        catalog_path=catalog_path,
    )


def _make_current_agent(catalog_path: Path, strategy: dict[str, Any]) -> NeeShopsAgent:
    """Build the current ranker with the same shared token index as production."""
    agent = _make_agent(IdentityRanker(), catalog_path, strategy)
    agent.ranker = ConstraintAwareRanker(
        strategy=strategy,
        token_index=agent.token_index,
    )
    return agent


def _evaluate_worker(
    arm: str,
    dataset_path: str,
    catalog_path: str,
    strategy: dict[str, Any],
    output: Any,
) -> None:
    """Evaluate one arm in a clean process so caches cannot leak across arms."""
    try:
        logging.getLogger("neeshops").setLevel(logging.WARNING)
        dataset = Path(dataset_path)
        catalog = Path(catalog_path)
        samples = load_jsonl(dataset)
        catalog_ids, categories, products = catalog_index(catalog)
        if arm == "identity":
            agent = _make_agent(IdentityRanker(), catalog, strategy)
        elif arm == "current":
            agent = _make_current_agent(catalog, strategy)
        else:
            raise ValueError(f"unknown evaluation arm: {arm}")
        result = evaluate(agent, samples, catalog_ids, categories, products)
        output.put({"result": result})
    except BaseException as exc:  # pragma: no cover - defensive worker boundary
        output.put({"error": f"{type(exc).__name__}: {exc}"})


def evaluate_isolated(
    arm: str,
    dataset_path: Path,
    catalog_path: Path,
    strategy: dict[str, Any],
) -> dict[str, Any]:
    """Run one evaluator arm in a fresh spawned interpreter."""
    context = get_context("spawn")
    output = context.Queue()
    process = context.Process(
        target=_evaluate_worker,
        args=(arm, str(dataset_path), str(catalog_path), strategy, output),
    )
    process.start()
    try:
        payload = output.get(timeout=1800)
    except Empty as exc:  # pragma: no cover - only on a stuck/crashed child
        process.terminate()
        process.join()
        raise RuntimeError(f"evaluation arm {arm!r} timed out") from exc
    process.join()
    if process.exitcode != 0:
        raise RuntimeError(f"evaluation arm {arm!r} exited with {process.exitcode}")
    if "error" in payload:
        raise RuntimeError(f"evaluation arm {arm!r} failed: {payload['error']}")
    return payload["result"]


def _delta(after: dict[str, Any], before: dict[str, Any], key: str) -> float:
    return round(float(after[key]) - float(before[key]), 6)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/dev_split.jsonl")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--personalization-weight", type=float)
    parser.add_argument("--rerank-limit", type=int)
    parser.add_argument("--label", default="person3b_personalization_ab")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    dataset_path = Path(args.dataset)
    if not catalog_path.exists() or not dataset_path.exists():
        print("Dataset or catalog unavailable; no metrics were fabricated.", file=sys.stderr)
        return 1

    base_strategy = load_strategy()
    deterministic = base_strategy["ranking"]["deterministic"]
    weight = (
        float(args.personalization_weight)
        if args.personalization_weight is not None
        else float(deterministic["weights"]["personalization"])
    )
    rerank_limit = (
        int(args.rerank_limit)
        if args.rerank_limit is not None
        else int(deterministic["rerank_limit"])
    )
    if weight < 0 or rerank_limit <= 0:
        parser.error("weight must be non-negative and rerank limit must be positive")

    no_profile_strategy = strategy_with_personalization(base_strategy, 0.0, rerank_limit)
    personalized_strategy = strategy_with_personalization(base_strategy, weight, rerank_limit)
    samples = load_jsonl(dataset_path)
    logging.getLogger("neeshops").setLevel(logging.WARNING)

    print(f"Evaluating {len(samples)} sessions from {dataset_path} ...")
    print(
        "  current ranker: ConstraintAwareRanker "
        f"(personalization weight={weight:g}, rerank limit={rerank_limit})\n"
    )
    identity = evaluate_isolated("identity", dataset_path, catalog_path, no_profile_strategy)
    unpersonalized = evaluate_isolated(
        "current", dataset_path, catalog_path, no_profile_strategy
    )
    personalized = evaluate_isolated(
        "current", dataset_path, catalog_path, personalized_strategy
    )

    ranking_mrr_delta = _delta(unpersonalized, identity, "mrr")
    personalization_mrr_delta = _delta(personalized, unpersonalized, "mrr")
    ranking_hit_delta = _delta(unpersonalized, identity, "hit_rate_at_10")
    personalization_hit_delta = _delta(personalized, unpersonalized, "hit_rate_at_10")

    print(f"  retrieval-only MRR:             {identity['mrr']}")
    print(f"  current ranker, profile off:    {unpersonalized['mrr']}")
    print(f"  current ranker, profile on:     {personalized['mrr']}")
    print(f"  ranking MRR delta:              {ranking_mrr_delta:+.6f}")
    print(f"  personalization-only MRR delta: {personalization_mrr_delta:+.6f}\n")
    print(f"  retrieval-only Hit@10:          {identity['hit_rate_at_10']}")
    print(f"  current ranker, profile off:    {unpersonalized['hit_rate_at_10']}")
    print(f"  current ranker, profile on:     {personalized['hit_rate_at_10']}")
    print(f"  ranking Hit@10 delta:           {ranking_hit_delta:+.6f}")
    print(f"  personalization-only Hit delta: {personalization_hit_delta:+.6f}")

    identity_by_id = {row["sample_id"]: row for row in identity["sessions"]}
    unpersonalized_by_id = {
        row["sample_id"]: row for row in unpersonalized["sessions"]
    }
    personalized_by_id = {row["sample_id"]: row for row in personalized["sessions"]}
    per_sample = [
        {
            "sample_id": sample_id,
            "scenario_type": baseline["scenario_type"],
            "retrieval_rank": baseline["best_rank"],
            "unpersonalized_rank": unpersonalized_by_id[sample_id]["best_rank"],
            "personalized_rank": personalized_by_id[sample_id]["best_rank"],
            "retrieval_reciprocal_rank": baseline["reciprocal_rank"],
            "unpersonalized_reciprocal_rank": unpersonalized_by_id[sample_id]["reciprocal_rank"],
            "personalized_reciprocal_rank": personalized_by_id[sample_id]["reciprocal_rank"],
        }
        for sample_id, baseline in identity_by_id.items()
    ]

    summary = {
        "experiment": "P3-D5 current-ranker personalization isolation",
        "dataset": str(dataset_path),
        "catalog": str(catalog_path),
        "sample_count": len(samples),
        "ranker": ConstraintAwareRanker.name,
        "configuration": {
            "personalization_weight": weight,
            "rerank_limit": rerank_limit,
            "llm_reranker": False,
        },
        "retrieval_only": identity,
        "current_ranker_without_personalization": unpersonalized,
        "current_ranker_with_personalization": personalized,
        "ranking_mrr_delta": ranking_mrr_delta,
        "personalization_mrr_delta": personalization_mrr_delta,
        "ranking_hit_rate_at_10_delta": ranking_hit_delta,
        "personalization_hit_rate_at_10_delta": personalization_hit_delta,
        "per_sample": per_sample,
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / f"{args.label}_{int(time.time())}.json"
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved full P3-D5 result to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
