#!/usr/bin/env python3
"""Run one or more experiments through neeshops.research against the dev
split, compare to a recorded baseline, and print/store accept-reject
outcomes.

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
from neeshops.research.experiment_runner import ExperimentRunner
from neeshops.research.optimizer import next_experiments, propose_grid, propose_random
from neeshops.research.results_store import ResultsStore
from starter.agent import Agent

# Organiser's published weak-baseline reference (docs/baseline_results.json).
# Prefer a freshly recorded run from `python scripts/evaluate.py` once the
# catalog is installed — pass --baseline-file to point at one.
PLACEHOLDER_BASELINE = {
    "hit_rate_at_10": 0.125,
    "mrr": 0.068034,
    "mttc": 9.81,
    "recommended_technical_score": 0.10671,
}


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
    parser.add_argument("--targeted", action="store_true", help="Generate experiments targeting the weakest scenario in baseline")
    parser.add_argument("--dataset", default="data/dev_split.jsonl")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--baseline-score", type=float, default=None, help="Explicit baseline score to beat (default: auto-evaluated on --dataset)")
    args = parser.parse_args()

    if not Path(args.catalog).exists():
        print(f"Catalog not found at {args.catalog}. See data/README.md.")
        return 1
    if not Path(args.dataset).exists():
        print(f"{args.dataset} not found — run scripts/create_dev_split.py first.")
        return 1

    eval_fn = _make_evaluate_fn(args.catalog)
    runner = ExperimentRunner(evaluate_fn=eval_fn, results_store=ResultsStore())

    if args.baseline_score is not None:
        baseline = {
            "technical_score": args.baseline_score,
            "recommended_technical_score": args.baseline_score,
            "scenario_metrics": {},
        }
    else:
        print(f"Measuring baseline on {args.dataset} using default strategy...")
        from neeshops.config.settings import load_strategy
        default_strat = load_strategy()
        baseline = eval_fn(default_strat, args.dataset)
        print(f"Baseline technical_score on {args.dataset}: {baseline.get('technical_score'):.6f}\n")

    if args.grid:
        param, *values = args.grid
        experiments = propose_grid(param, [float(v) for v in values])
    elif args.random:
        experiments = propose_random(n=args.random)
    elif args.targeted:
        experiments = next_experiments(baseline.get("scenario_metrics", {}))
        print(f"Generated {len(experiments)} scenario-targeted experiment(s):")
        for e in experiments:
            print(f"  - [{e.name}] {e.hypothesis}")
        print()
    else:
        parser.error("Pass --grid PARAM v1 v2 ..., --random N, or --targeted")
        return 2

    for experiment in experiments:
        record = runner.run(experiment, dataset_path=args.dataset, baseline_metrics=baseline)
        status = "ACCEPTED" if record["accepted"] else "rejected"
        print(f"[{status}] {experiment.name}: {experiment.parameters}")
        print(f"  technical_score: {record['metrics'].get('recommended_technical_score')} (baseline: {baseline.get('technical_score'):.6f})")
        print(f"  latency: {record.get('latency_seconds')}s | tokens: {record.get('tokens', {}).get('total_tokens', 0)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
