"""Validate the real adapter output against the official response rules.

The fixture deliberately contains a searchable product so recommendation
assertions cannot pass vacuously when the full 50k catalog is absent in CI.
"""
import json

import pytest

from starter.agent import Agent


ALLOWED_ATTRIBUTES = {
    "category", "material", "color", "size", "style", "brand", "budget",
    "feature", "use_case", "other", None,
}


@pytest.fixture
def agent(tmp_path):
    catalog_path = tmp_path / "catalog.jsonl"
    rows = [
        {
            "parent_asin": f"B00{index}",
            "title": f"Black running shoes model {index}",
            "categories": ["Shoes"],
            "features": ["comfortable sneaker"],
            "details": {"color": "black"},
            "store": "Example",
            "description": ["daily running shoe"],
            "price": 70.0 + index,
        }
        for index in range(1, 7)
    ]
    catalog_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return Agent(catalog_path)


def test_agent_exposes_required_methods(agent):
    assert hasattr(agent, "reset")
    assert hasattr(agent, "respond")


def test_respond_returns_exact_official_top_level_keys(agent):
    agent.reset("s1", user_profile={})
    result = agent.respond("s1", "black running shoes", turn=1, top_k=10)

    assert set(result) == {"message", "ask_attribute", "recommendations", "usage"}
    assert isinstance(result["message"], str)
    assert result["ask_attribute"] in ALLOWED_ATTRIBUTES
    assert isinstance(result["recommendations"], list)
    assert set(result["usage"]) == {"prompt_tokens", "completion_tokens"}
    assert all(isinstance(value, int) and value >= 0 for value in result["usage"].values())


def test_respond_recommendation_shape_is_non_vacuous(agent):
    agent.reset("s2", user_profile={})
    result = agent.respond("s2", "black running shoes", turn=1, top_k=10)

    assert result["recommendations"], "fixture query should return a product"
    for recommendation in result["recommendations"]:
        assert set(recommendation) <= {"parent_asin", "score"}
        assert isinstance(recommendation["parent_asin"], str)
        assert recommendation["parent_asin"]
        if "score" in recommendation:
            assert isinstance(recommendation["score"], (int, float))
