"""Tests for the interactive demo (scripts/interactive_demo.py).

Verifies:
- Profile normalization rules.
- HTTP routes / payload schemas.
- Ranking provenance and candidate pool funnel metrics.
- Baseline vs Final ranking toggle behavior without mutating default strategy.
- Sampled session initialization, stepwise trajectory, and completion triggers.
- PAGE UI invariants and freeze banner string.
"""

from __future__ import annotations

import copy
import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.interactive_demo import (
    FREEZE_BANNER,
    PAGE,
    SAMPLED_SESSIONS,
    DemoState,
    _provenance_entry,
    _run_turn,
    advance_sampled_session,
    enrich,
    enrich_pool,
    normalize_demo_profile,
    pool_stats,
    provenance_for,
    start_sampled_session,
)


def test_normalize_demo_profile_defaults_and_validation():
    assert normalize_demo_profile(None) == {"preference_tags": []}
    assert normalize_demo_profile({}) == {"preference_tags": []}

    profile = {
        "preference_tags": [" comfort ", "durability", "comfort", ""],
        "purchase_frequency": "weekly",
        "invalid_field": "ignored",
    }
    normalized = normalize_demo_profile(profile)
    assert "invalid_field" not in normalized
    assert normalized["purchase_frequency"] == "weekly"
    assert normalized["preference_tags"] == ["comfort", "durability"]

    with pytest.raises(ValueError, match="user_profile must be an object"):
        normalize_demo_profile("not a dict")

    with pytest.raises(ValueError, match="preference_tags must be a list"):
        normalize_demo_profile({"preference_tags": "not a list"})


def test_page_contains_banner_and_sample_options():
    assert FREEZE_BANNER in PAGE
    assert "submission-freeze" in PAGE
    assert "deterministic ranker" in PAGE
    for s in SAMPLED_SESSIONS:
        assert s["sample_id"] in PAGE


def test_provenance_helpers_structure():
    mock_entry = MagicMock()
    mock_entry.features.coverage = 0.85
    mock_entry.features.salience = 0.45
    mock_entry.features.popularity = 0.62
    mock_entry.features.hard_constraint_violation_count = 0
    mock_entry.features.retrieval_rank = 12
    mock_entry.features.active_constraint_count = 2
    mock_entry.constraint_evaluation.soft_matches = ["running", "cushion"]
    mock_entry.constraint_evaluation.hard_violations = []

    res = _provenance_entry(mock_entry)
    assert res is not None
    assert res["coverage"] == 0.85
    assert res["salience"] == 0.45
    assert res["popularity"] == 0.62
    assert res["violations"] == 0
    assert res["pool_rank"] == 12
    assert res["active_constraints"] == 2
    assert "running" in res["soft_matches"]


def test_enrich_and_pool_stats():
    DemoState.lookup = {
        "B001": {
            "title": "Running Shoes",
            "price": 89.99,
            "store": "Brand A",
            "average_rating": 4.5,
            "categories": ["Shoes", "Running Shoes"],
        }
    }
    recs = [{"parent_asin": "B001", "score": 0.95}]
    enriched = enrich(recs)
    assert len(enriched) == 1
    assert enriched[0]["title"] == "Running Shoes"
    assert enriched[0]["price"] == "$89.99"
    assert enriched[0]["image"].endswith("B001.01._SL400_.jpg")

    mock_cand = MagicMock()
    mock_cand.parent_asin = "B001"
    mock_cand.score = 0.95
    mock_cand.source = "bm25+semantic"
    stats = pool_stats([mock_cand])
    assert stats["n"] == 1
    assert stats["sources"]["both"] == 1
    assert stats["price_coverage"]["priced"] == 1


def test_baseline_ranker_immutability():
    DemoState.init()
    orig_strategy = copy.deepcopy(DemoState.impl.strategy)

    baseline_ranker = DemoState.baseline_ranker()
    assert baseline_ranker is not None
    assert baseline_ranker._coverage_salience_weight == 0.5
    assert baseline_ranker._buying_salience_weight == 0.5

    # Confirm default production strategy was NOT mutated
    assert DemoState.impl.strategy == orig_strategy


def test_run_turn_payload_and_diagnostics():
    DemoState.init()
    session_id = "test_turn_sess"
    DemoState.impl.reset(session_id, {"preference_tags": ["comfort"]})
    DemoState.clear_session(session_id)

    payload = _run_turn(session_id, "I need running shoes under $100", 1)
    assert "message" in payload
    assert "recommendations" in payload
    assert "baseline" in payload
    assert "debug" in payload
    assert isinstance(payload["recommendations"], list)
    assert len(payload["recommendations"]) <= 10

    debug = payload["debug"]
    assert "catalog" in debug
    assert "hybrid" in debug
    assert "pool" in debug
    assert "scored" in debug
    assert "latency_ms" in debug
    assert debug["usage"]["prompt_tokens"] == 0
    assert debug["usage"]["cost"] == 0.0


def test_sampled_session_lifecycle():
    DemoState.init()
    # Check sample session start
    sample_id = "public_0112"
    start_info = start_sampled_session(sample_id)
    assert start_info["sample_id"] == sample_id
    assert "session_id" in start_info
    assert "user_message" in start_info
    assert start_info["target"]["parent_asin"] != ""

    session_id = start_info["session_id"]
    turn_payload = advance_sampled_session(session_id)
    assert turn_payload["turn"] == 1
    assert "trajectory" in turn_payload
    assert "session_over" in turn_payload
    assert "recommendations" in turn_payload
