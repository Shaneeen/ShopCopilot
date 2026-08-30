"""Validate the real adapter output against the official response rules (P5-D1).

The fixture deliberately contains searchable products so recommendation
assertions cannot pass vacuously when the full 50k catalog is absent in CI.
Enforces strict compliance with docs/agent_api_contract.json:
- top_k=10
- non-empty recommendations
- additionalProperties: false on turn_response, recommendations items, and usage
- allowed ask_attribute enum values
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from starter.agent import Agent

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "docs" / "agent_api_contract.json"


@pytest.fixture(scope="session")
def contract_schema() -> dict[str, Any]:
    with open(CONTRACT_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def agent(tmp_path: Path) -> Agent:
    catalog_path = tmp_path / "catalog.jsonl"
    rows = [
        {
            "parent_asin": f"B00{index:02d}",
            "title": f"Black running shoes model {index}",
            "categories": ["Shoes", "Athletic"],
            "features": ["comfortable sneaker", "breathable running footwear"],
            "details": {"color": "black", "material": "mesh"},
            "store": "Example",
            "description": ["daily running shoe"],
            "price": 70.0 + index,
        }
        for index in range(1, 15)
    ]
    catalog_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return Agent(catalog_path)


def validate_against_contract(
    response: dict[str, Any],
    contract_schema: dict[str, Any],
    top_k: int = 10,
    require_non_empty_recommendations: bool = True,
) -> None:
    """Strictly validate turn_response against docs/agent_api_contract.json.

    Enforces:
    - additionalProperties: false (no forbidden top-level or nested keys)
    - required keys present and correct types
    - ask_attribute in allowed enum
    - recommendations non-empty (when required) and bounded by top_k (max 10)
    - each recommendation item adheres to required/optional/additionalProperties rules
    - usage token counts are non-negative integers
    """
    assert isinstance(response, dict), f"Expected dict response, got {type(response)}"

    turn_schema = contract_schema["turn_response"]
    expected_top_level_props = set(turn_schema["properties"].keys())
    required_top_level_keys = set(turn_schema["required"])

    # additionalProperties: false on top-level response
    response_keys = set(response.keys())
    assert response_keys.issubset(expected_top_level_props), (
        f"Forbidden additional properties in response: {response_keys - expected_top_level_props}"
    )

    # required top-level keys
    assert required_top_level_keys.issubset(response_keys), (
        f"Missing required top-level keys: {required_top_level_keys - response_keys}"
    )

    # message: string
    assert isinstance(response["message"], str) and response["message"], (
        "message must be a non-empty string"
    )

    # ask_attribute: enum or null
    allowed_attributes = set(turn_schema["properties"]["ask_attribute"]["enum"])
    assert response["ask_attribute"] in allowed_attributes, (
        f"ask_attribute {response['ask_attribute']!r} not in {allowed_attributes}"
    )

    # recommendations: array, maxItems: 100, bounded by top_k
    recs = response["recommendations"]
    assert isinstance(recs, list), f"recommendations must be a list, got {type(recs)}"
    assert len(recs) <= turn_schema["properties"]["recommendations"].get("maxItems", 100)
    assert len(recs) <= top_k, f"recommendations count {len(recs)} exceeded top_k={top_k}"

    if require_non_empty_recommendations:
        assert len(recs) > 0, "Expected non-empty recommendations for relevant query"

    rec_item_schema = turn_schema["properties"]["recommendations"]["items"]
    rec_allowed_props = set(rec_item_schema["properties"].keys())
    rec_required_keys = set(rec_item_schema["required"])

    for idx, rec in enumerate(recs):
        assert isinstance(rec, dict), f"Recommendation {idx} must be a dict"
        rec_keys = set(rec.keys())

        # additionalProperties: false on recommendation items
        assert rec_keys.issubset(rec_allowed_props), (
            f"Recommendation {idx} has forbidden properties: {rec_keys - rec_allowed_props}"
        )
        # required keys on item (parent_asin)
        assert rec_required_keys.issubset(rec_keys), (
            f"Recommendation {idx} missing required keys: {rec_required_keys - rec_keys}"
        )
        # parent_asin: string minLength >= 1
        assert isinstance(rec["parent_asin"], str) and len(rec["parent_asin"]) >= 1, (
            f"Invalid parent_asin in recommendation {idx}: {rec.get('parent_asin')}"
        )
        # score (optional number)
        if "score" in rec:
            assert isinstance(rec["score"], (int, float)) and not isinstance(rec["score"], bool), (
                f"Invalid score type in recommendation {idx}: {type(rec['score'])}"
            )

    # usage: object, additionalProperties: false, required: [prompt_tokens, completion_tokens]
    if "usage" in response:
        usage = response["usage"]
        assert isinstance(usage, dict), f"usage must be a dict, got {type(usage)}"
        usage_schema = turn_schema["properties"]["usage"]
        usage_allowed_props = set(usage_schema["properties"].keys())
        usage_required_keys = set(usage_schema["required"])

        # additionalProperties: false on usage
        usage_keys = set(usage.keys())
        assert usage_keys.issubset(usage_allowed_props), (
            f"usage has forbidden properties: {usage_keys - usage_allowed_props}"
        )
        assert usage_required_keys.issubset(usage_keys), (
            f"usage missing required keys: {usage_required_keys - usage_keys}"
        )
        assert isinstance(usage["prompt_tokens"], int) and not isinstance(usage["prompt_tokens"], bool)
        assert usage["prompt_tokens"] >= 0
        assert isinstance(usage["completion_tokens"], int) and not isinstance(usage["completion_tokens"], bool)
        assert usage["completion_tokens"] >= 0


def test_agent_exposes_required_methods(agent: Agent) -> None:
    assert hasattr(agent, "reset")
    assert hasattr(agent, "respond")


def test_contract_schema_file_exists_and_valid(contract_schema: dict[str, Any]) -> None:
    assert "reset_request" in contract_schema
    assert "turn_request" in contract_schema
    assert "turn_response" in contract_schema
    assert contract_schema["turn_request"]["properties"]["top_k"]["const"] == 10
    assert contract_schema["turn_response"]["additionalProperties"] is False


def test_respond_strict_contract_validation_top_k_10(
    agent: Agent, contract_schema: dict[str, Any]
) -> None:
    agent.reset("s1", user_profile={})
    result = agent.respond("s1", "black running shoes", turn=1, top_k=10)

    # Strict contract validation with non-empty recommendations and top_k=10
    validate_against_contract(
        result,
        contract_schema=contract_schema,
        top_k=10,
        require_non_empty_recommendations=True,
    )
    assert len(result["recommendations"]) == 10, (
        f"Expected exactly top_k=10 recommendations when catalog has sufficient matches, got {len(result['recommendations'])}"
    )


def test_respond_strips_internal_fields_and_preserves_additional_properties_false(
    agent: Agent, contract_schema: dict[str, Any]
) -> None:
    agent.reset("s2", user_profile={})
    result = agent.respond("s2", "black running shoes", turn=1, top_k=10)

    # Ensure internal NeeShopsAgent fields (route, reason, etc.) never leak to official output
    assert "route" not in result
    for rec in result["recommendations"]:
        assert "reason" not in rec
        assert "title" not in rec
        assert "categories" not in rec

    validate_against_contract(
        result,
        contract_schema=contract_schema,
        top_k=10,
        require_non_empty_recommendations=True,
    )


def test_multi_turn_conversation_strict_contract(
    agent: Agent, contract_schema: dict[str, Any]
) -> None:
    agent.reset("s3", user_profile={})

    # Turn 1: Initial broad query
    res1 = agent.respond("s3", "running shoes", turn=1, top_k=10)
    validate_against_contract(res1, contract_schema, top_k=10, require_non_empty_recommendations=True)

    # Turn 2: Clarification / preference refinement
    res2 = agent.respond("s3", "I prefer black mesh shoes under $80", turn=2, top_k=10)
    validate_against_contract(res2, contract_schema, top_k=10, require_non_empty_recommendations=True)

    # Turn 3: Intent override
    res3 = agent.respond("s3", "Actually, I need white shoes instead", turn=3, top_k=10)
    validate_against_contract(res3, contract_schema, top_k=10, require_non_empty_recommendations=False)


def test_reset_accepts_valid_contract_user_profile(
    agent: Agent, contract_schema: dict[str, Any]
) -> None:
    valid_profile = {
        "purchase_frequency": "frequent",
        "average_prior_rating": 4.5,
        "rating_style": "generous",
        "preference_tags": ["shoes", "comfort"],
        "summary": "Shopper looking for comfortable running sneakers",
    }
    agent.reset("s4", user_profile=valid_profile)
    result = agent.respond("s4", "black shoes", turn=1, top_k=10)
    validate_against_contract(result, contract_schema, top_k=10, require_non_empty_recommendations=True)
