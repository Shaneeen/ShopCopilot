#!/usr/bin/env python3
"""Wrapper around the official evaluator (`evaluator/local_evaluator.py`) —
never reimplements scoring. Prefer `python3 -m evaluator.local_evaluator`
directly (the documented competition command, writes `results.json`) when
you just want the official run; use this script when you also want the
metrics archived under `artifacts/experiments/` for comparison by
`neeshops/research/` (e.g. as a recorded baseline for `scripts/run_experiment.py`).

    python scripts/evaluate.py [--dataset data/public_set.jsonl] [--catalog data/catalog.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from starter.agent import Agent

ARTIFACTS_DIR = Path("artifacts/experiments")


def run_official_evaluator(dataset_path: str, catalog_path: str = "data/catalog.jsonl") -> dict:
    """Run the real official evaluator against `dataset_path` and return its
    metrics dict — the same shape `evaluator.local_evaluator.evaluate()`
    returns (hit_rate_at_10, mrr, mttc, efficiency,
    recommended_technical_score, reported_token_usage, scenario_metrics,
    sessions, ...).
    """
    samples = load_jsonl(dataset_path)
    catalog_ids, categories, products = catalog_index(catalog_path)
    agent = Agent(catalog_path)
    return evaluate(agent, samples, catalog_ids, categories, products)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--label", default="run")
    args = parser.parse_args()

    if not Path(args.catalog).exists():
        print(
            f"Catalog not found at {args.catalog}. See data/README.md — "
            "download it from the GitHub Release first."
        )
        return 1

    result = run_official_evaluator(args.dataset, args.catalog)

    print("Evaluation results:")
    for key in ("sample_count", "hit_rate_at_10", "mrr", "mttc", "efficiency", "recommended_technical_score"):
        print(f"  {key:28s} {result.get(key)}")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / f"{args.label}_{int(time.time())}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved full results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
