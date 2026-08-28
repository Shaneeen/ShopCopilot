#!/usr/bin/env python3
"""Five scripted conversation scenarios against the real agent — a readable
smoke test of intent routing, clarification, override and no-preference
handling. (The oracle simulation lives in scripts/run_oracle_eval.py.)

    python scripts/run_test_cases.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("NEESHOPS_LOG_LEVEL", "ERROR")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starter.agent import Agent  # noqa: E402

SCENARIOS: list[tuple[str, list[str]]] = [
    (
        "Buying — full requirements up front",
        [
            "I need casual women's shoes under $120",
            "Sneakers please",
            "Leather is fine",
            "No preference on color",
        ],
    ),
    (
        "Browsing — exploratory, wants suggestions",
        [
            "I want to refresh my wardrobe with something cozy for winter",
            "Something soft and warm",
        ],
    ),
    (
        "Intent override — changes their mind mid-conversation",
        [
            "I'm looking for a jacket. A key requirement is: color: blue.",
            "Actually, ignore my earlier preference. What I need is: black leather jacket under $80.",
            "Under $60 is even better",
        ],
    ),
    (
        "Boundary — no preference, wants the agent to decide",
        [
            "I need a gift for my sister's birthday",
            "I don't have a preference for material; please use your judgment.",
            "Around $30",
        ],
    ),
    (
        "Feature-driven — cares about a specific attribute",
        [
            "I'm looking for running shoes. A key requirement is: cushioning.",
            "Mesh fabric",
            "Wide fit",
        ],
    ),
]


def main() -> int:
    agent = Agent()
    lookup = agent._impl.catalog_lookup

    for idx, (name, messages) in enumerate(SCENARIOS, start=1):
        session_id = f"testcase_{idx}"
        agent.reset(session_id, user_profile={"preference_tags": ["comfort"]})
        print(f"\n{'=' * 70}\nScenario {idx}: {name}\n{'=' * 70}")
        for turn, message in enumerate(messages, start=1):
            result = agent.respond(session_id, message, turn=turn, top_k=10)
            print(f"\n  [user]  {message}")
            asked = result.get("ask_attribute")
            if asked:
                print(f"  [agent] {result['message']}   (asking about: {asked})")
            else:
                print(f"  [agent] {result['message']}")
            for rec in result["recommendations"][:3]:
                row = lookup.get(rec["parent_asin"], {})
                price = row.get("price")
                price_s = f"${price:.2f}" if isinstance(price, (int, float)) else "price n/a"
                title = str(row.get("title", rec["parent_asin"]))[:70]
                print(f"     - {rec['parent_asin']}  {price_s:<12} {title}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
