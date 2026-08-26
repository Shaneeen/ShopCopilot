#!/usr/bin/env python3
"""Sanity-check that starter.agent.Agent runs end-to-end without invoking
the full official evaluator — a fast smoke check while iterating.

    python scripts/run_baseline.py

For the real scored run, use `python3 -m evaluator.local_evaluator` (the
official documented command) or `python scripts/evaluate.py` (same
evaluator, also archives results under artifacts/experiments/).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starter.agent import Agent


def main() -> int:
    agent = Agent()
    session_id = "smoke-test-session"
    agent.reset(session_id, user_profile={"preference_tags": ["comfort"]})

    turns = [
        "I need casual women's shoes under $120",
        "Sneakers, please",
    ]
    for turn_idx, message in enumerate(turns, start=1):
        result = agent.respond(session_id, message, turn=turn_idx, top_k=10)
        print(f"\nTurn {turn_idx}: {message!r}")
        print(f"  message: {result['message']}")
        print(f"  ask_attribute: {result['ask_attribute']}")
        print(f"  recommendations: {len(result['recommendations'])}")
        for rec in result["recommendations"][:3]:
            print(f"    - {rec['parent_asin']} (score={rec['score']:.3f})")

    print(
        "\nDone. If recommendations is 0 for every turn, install the "
        "catalog at data/catalog.jsonl — see data/README.md."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
