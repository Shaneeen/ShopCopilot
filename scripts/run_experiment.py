#!/usr/bin/env python3
"""Run one or more experiments through neeshops.research against the dev
split. First measure the unchanged default strategy on that same dataset,
then print/store each candidate's accept-reject outcome.

    python scripts/run_experiment.py --grid retrieval.browsing.semantic_weight 0.3 0.5 0.7 0.9
    python scripts/run_experiment.py --random 5
    python scripts/run_experiment.py --targeted

Uses the real official evaluator (`evaluator/local_evaluator.py`) via
`starter.agent.Agent(catalog_path, strategy=...)` — the `strategy` kwarg is
a NeeShops-only extension (see `starter/agent.py`); the official evaluator
never passes it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from neeshops.config.settings import load_strategy
from neeshops.research.experiment_runner import ExperimentRunner
from neeshops.research.optimizer import next_experiments, propose_grid, propose_random
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
        result["technical_score"] = result.get("recommended_technical_score", 0.0)
        return result

    return _evaluate_fn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", nargs="+", metavar=("PARAM", "VALUES"), help="Parameter dot-path and candidate values")
    parser.add_argument("--random", type=int, metavar="N", help="Propose N random parameter experiments")
    parser.add_argument("--targeted", action="store_true", help="Generate experiments targeting the weakest scenario in baseline")
    parser.add_argument("--dataset", default="data/dev_split.jsonl", help="Dataset split path")
    parser.add_argument("--catalog", default="data/catalog.jsonl", help="Catalog jsonl path")
    parser.add_argument("--baseline-file", type=Path, default=None, help="Path to a baseline JSON file (from scripts/evaluate.py)")
    parser.add_argument("--baseline-score", type=float, default=None, help="Explicit baseline score to beat (default: auto-evaluated on --dataset)")
    parser.add_argument("--min-improvement", type=float, default=0.0, help="Minimum technical_score improvement required to accept")
    parser.add_argument("--seed", type=int, default=42, help="seed for --random proposals")
    args = parser.parse_args()

    if not Path(args.catalog).exists():
        print(f"Catalog not found at {args.catalog}. See data/README.md.")
        return 1
    if not Path(args.dataset).exists():
        print(f"{args.dataset} not found — run scripts/create_dev_split.py first.")
        return 1

    eval_fn = _make_evaluate_fn(args.catalog)
    runner = ExperimentRunner(
        evaluate_fn=eval_fn,
        results_store=ResultsStore(),
        min_improvement=args.min_improvement,
    )

    if args.baseline_file is not None:
        if not args.baseline_file.exists():
            print(f"Baseline file not found at {args.baseline_file}")
            return 1
        with open(args.baseline_file, "r", encoding="utf-8") as f:
            baseline = json.load(f)
        if "technical_score" not in baseline and "recommended_technical_score" in baseline:
            baseline["technical_score"] = baseline["recommended_technical_score"]
        print(f"Loaded baseline from {args.baseline_file}: technical_score={baseline.get('technical_score', 0.0):.6f}\n")
    elif args.baseline_score is not None:
        baseline = {
            "technical_score": args.baseline_score,
            "recommended_technical_score": args.baseline_score,
            "scenario_metrics": {},
        }
        print(f"Using explicit baseline technical_score: {args.baseline_score:.6f}\n")
    else:
        print(f"Measuring baseline on {args.dataset} using default strategy...")
        from neeshops.config.settings import load_strategy
        default_strat = load_strategy()
        baseline = eval_fn(default_strat, args.dataset)
        print(f"Baseline technical_score on {args.dataset}: {baseline.get('technical_score', 0.0):.6f}\n")

    if args.grid:
        if len(args.grid) < 2:
            parser.error("Pass --grid PARAM v1 v2 ... (at least one value required)")
            return 2
        param, *raw_values = args.grid
        try:
            values = [float(v) for v in raw_values]
        except ValueError as e:
            parser.error(f"Invalid float value in --grid: {e}")
            return 2
        experiments = propose_grid(param, values)
    elif args.random:
        experiments = propose_random(n=args.random, seed=args.seed)
    elif args.targeted:
        scenario_metrics = baseline.get("scenario_metrics", {})
        if not scenario_metrics:
            print("Note: No scenario breakdown available in baseline; falling back to random sampling.")
        experiments = next_experiments(scenario_metrics)
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
        cand_score = record["metrics"].get("recommended_technical_score", 0.0)
        base_score = baseline.get("technical_score", 0.0)
        print(f"[{status}] {experiment.name}: {experiment.parameters}")
        print(f"  technical_score: {cand_score:.6f} (baseline: {base_score:.6f})")
        print(f"  latency: {record.get('latency_seconds')}s | tokens: {record.get('tokens', {}).get('total_tokens', 0)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
