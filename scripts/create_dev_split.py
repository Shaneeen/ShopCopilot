#!/usr/bin/env python3
"""Deterministically split the 200 public labelled sessions into an
internal train/holdout split, so experiments aren't all tuned against every
labelled example we have (the private eval set has 800 unseen sessions —
see docs/neeshops/COMPETITION_NOTES.md).

    python scripts/create_dev_split.py [--train-ratio 0.8] [--seed 42]

Writes data/dev_split.jsonl and data/holdout_split.jsonl (both gitignored —
regenerate rather than commit, so everyone gets the same split from the
same seed).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neeshops.config.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.public_set_path.exists():
        print(
            f"Public session set not found at {settings.public_set_path}.\n"
            "See data/README.md for how to install it before running this script."
        )
        return 1

    with open(settings.public_set_path, encoding="utf-8") as f:
        sessions = [json.loads(line) for line in f if line.strip()]

    rng = random.Random(args.seed)
    shuffled = sessions[:]
    rng.shuffle(shuffled)

    split_idx = round(len(shuffled) * args.train_ratio)
    train, holdout = shuffled[:split_idx], shuffled[split_idx:]

    train_path = settings.public_set_path.parent / "dev_split.jsonl"
    holdout_path = settings.public_set_path.parent / "holdout_split.jsonl"

    _write_jsonl(train_path, train)
    _write_jsonl(holdout_path, holdout)

    print(
        f"Split {len(sessions)} public sessions (seed={args.seed}) into:\n"
        f"  {train_path}  ({len(train)} sessions — for iterating on experiments)\n"
        f"  {holdout_path}  ({len(holdout)} sessions — check only occasionally, "
        "to catch overfitting to the dev split before the private eval)"
    )
    return 0


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
