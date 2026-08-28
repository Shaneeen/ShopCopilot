#!/usr/bin/env python3
"""Run one or more experiments through neeshops.research against the dev
split. First measure the unchanged default strategy on that same dataset,
then print/store each candidate's accept-reject outcome.

    python scripts/run_experiment.py --grid retrieval.browsing.semantic_weight 0.3 0.5 0.7 0.9
    python scripts/run_experiment.py --random 5

Uses the real official evaluator (`evaluator/local_evaluator.py`) via
`starter.agent.Agent(catalog_path, strategy=...)` — the `strategy` kwarg is
a NeeShops-only extension (see `starter/agent.py`); the official evaluator
never passes it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from neeshops.config.settings import load_strategy
from neeshops.research.experiment_runner import ExperimentRunner
from neeshops.research.optimizer import propose_grid, propose_random
from neeshops.research.results_store import ResultsStore
from starter.agent import Agent

def _make_evaluate_fn(catalog_path: str):
    catalog_ids, categories, products = catalog_index(catalog_path)

    def _evaluate_fn(strategy: dict, dataset_path: str) -> dict:
        samples = load_jsonl(dataset_path)
        agent = Agent(catalog_path, strategy=strategy)
        result = evaluate(agent, samples, catalog_ids, categories, products)
        # ExperimentRunner.PRIMARY_METRIC reads "technical_score"; the
        # official evaluator's key is "recommended_technical_score" — alias
        # it here rather than renaming either side's vocabulary.
        result["technical_score"] = result["recommended_technical_score"]
        return result

    return _evaluate_fn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", nargs="+", metavar=("PARAM", "VALUES"))
    parser.add_argument("--random", type=int, metavar="N")
    parser.add_argument("--dataset", default="data/dev_split.jsonl")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--seed", type=int, default=42, help="seed for --random proposals")
    args = parser.parse_args()

    if not Path(args.catalog).exists():
        print(f"Catalog not found at {args.catalog}. See data/README.md.")
        return 1
    if not Path(args.dataset).exists():
        print(f"{args.dataset} not found — run scripts/create_dev_split.py first.")
        return 1

    if args.grid:
        param, *values = args.grid
        experiments = propose_grid(param, [float(v) for v in values])
    elif args.random:
        experiments = propose_random(n=args.random, seed=args.seed)
    else:
        parser.error("Pass --grid PARAM v1 v2 ... or --random N")
        return 2

    evaluate_fn = _make_evaluate_fn(args.catalog)
    runner = ExperimentRunner(
        evaluate_fn=evaluate_fn, results_store=ResultsStore()
    )

    # Always measure the unchanged default strategy on the exact dataset used
    # by the candidates. The organizer's published 200-session weak-starter
    # score is a useful reference, but it is not a valid baseline for a
    # 160-session NeeShops development experiment.
    print(f"Measuring default-strategy baseline on {args.dataset} ...")
    baseline = evaluate_fn(load_strategy(), args.dataset)
    print(f"  baseline technical_score: {baseline['recommended_technical_score']}")

    for experiment in experiments:
        record = runner.run(experiment, dataset_path=args.dataset, baseline_metrics=baseline)
        status = "ACCEPTED" if record["accepted"] else "rejected"
        print(f"[{status}] {experiment.name}: {experiment.parameters}")
        print(f"  technical_score: {record['metrics'].get('recommended_technical_score')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
