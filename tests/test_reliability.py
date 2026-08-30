"""Reliability test suite for Agent edge cases, fault injection, and contract conformance (P5 stretch).

Validates that Agent NEVER raises an exception under:
- Missing catalog (returns valid response with 0 recommendations)
- Missing LLM key / disabled LLM (deterministic fallback)
- Empty or whitespace-only queries
- Malformed inputs, unicode/emojis, injection attempts, extreme payloads
- Subcomponent failures (crashed retriever, crashed ranker, crashed clarification engine)
- Out-of-bounds turn or top_k values
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from neeshops.agent import NeeShopsAgent
from neeshops.config.settings import load_strategy
from neeshops.models.session import ConversationState
from neeshops.ranking.base import Ranker
from neeshops.retrieval.base import Candidate, Retriever
from starter.agent import Agent


def _assert_valid_contract_response(res: dict[str, Any], top_k: int = 10) -> None:
    """Strictly assert response conforms to turn_response in agent_api_contract.json."""
    assert isinstance(res, dict), "Response must be a dict"
    assert "message" in res and isinstance(res["message"], str) and len(res["message"]) > 0
    assert "ask_attribute" in res
    assert res["ask_attribute"] in {
        "category", "material", "color", "size", "style", "brand",
        "budget", "feature", "use_case", "other", None,
    }
    assert "recommendations" in res and isinstance(res["recommendations"], list)
    assert len(res["recommendations"]) <= top_k
    for rec in res["recommendations"]:
        assert isinstance(rec, dict)
        assert "parent_asin" in rec and isinstance(rec["parent_asin"], str) and len(rec["parent_asin"]) > 0
        if "score" in rec and rec["score"] is not None:
            assert isinstance(rec["score"], (int, float)) and not isinstance(rec["score"], bool)

    assert "usage" in res and isinstance(res["usage"], dict)
    assert isinstance(res["usage"].get("prompt_tokens"), int) and res["usage"]["prompt_tokens"] >= 0
    assert isinstance(res["usage"].get("completion_tokens"), int) and res["usage"]["completion_tokens"] >= 0


def test_missing_catalog_returns_valid_response(tmp_path: Path) -> None:
    """Missing catalog file must return 0 candidates with a valid contract response."""
    nonexistent = tmp_path / "nonexistent_catalog.jsonl"
    agent = Agent(catalog_path=nonexistent)
    agent.reset("missing_cat_s1", user_profile={})

    res = agent.respond("missing_cat_s1", "black running shoes", turn=1, top_k=10)
    _assert_valid_contract_response(res, top_k=10)
    assert res["recommendations"] == []
    assert res["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


def test_empty_catalog_file_returns_valid_response(tmp_path: Path) -> None:
    """0-byte catalog file must return valid contract response with 0 recommendations."""
    empty_file = tmp_path / "empty_catalog.jsonl"
    empty_file.write_text("", encoding="utf-8")

    agent = Agent(catalog_path=empty_file)
    agent.reset("empty_cat_s1", user_profile={})

    res = agent.respond("empty_cat_s1", "running shoes under $50", turn=1, top_k=10)
    _assert_valid_contract_response(res, top_k=10)
    assert res["recommendations"] == []


def test_missing_llm_key_deterministic_fallback() -> None:
    """Strategy with enable_llm_reranker=True without API key falls back
    deterministically to the constraint-aware baseline ranker."""
    strategy = load_strategy()
    strategy["feature_flags"]["enable_semantic_retrieval"] = False
    strategy["feature_flags"]["enable_llm_reranker"] = True
    agent = Agent(strategy=strategy)
    agent.reset("llm_fallback_s1", user_profile={"preference_tags": ["comfort"]})

    res = agent.respond("llm_fallback_s1", "black sneakers", turn=1, top_k=10)
    _assert_valid_contract_response(res, top_k=10)
    assert res["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


def test_empty_and_whitespace_queries() -> None:
    """Empty, whitespace, tabs, and newlines must never crash the Agent."""
    agent = Agent()
    session_id = "whitespace_s1"
    agent.reset(session_id, user_profile={})

    test_queries = ["", "   ", "\t\t", "\n\n\r", "   \n\t   "]
    for turn_idx, q in enumerate(test_queries, start=1):
        res = agent.respond(session_id, q, turn=turn_idx, top_k=10)
        _assert_valid_contract_response(res, top_k=10)


def test_malformed_and_extreme_inputs() -> None:
    """Adversarial payloads, extreme lengths, emojis, and injections must not crash the Agent."""
    agent = Agent()
    session_id = "extreme_s1"
    agent.reset(session_id, user_profile={"invalid_list": [None, 123], "unknown_field": True})

    adversarial_messages = [
        "👟🔥🎉 跑步鞋 \u200b\u200c <script>alert('xss')</script>",
        "DROP TABLE products; SELECT * FROM catalog WHERE 1=1; --",
        "NULL\x00\x01\x02\x7f\xff bytes",
        "A" * 20000,  # 20k characters
        "shoes " * 5000,  # 5k words
    ]

    for turn_idx, message in enumerate(adversarial_messages, start=1):
        res = agent.respond(session_id, message, turn=turn_idx, top_k=10)
        _assert_valid_contract_response(res, top_k=10)


def test_boundary_turn_and_top_k_parameters() -> None:
    """Agent handles non-standard turn numbers and top_k bounds safely."""
    agent = Agent()
    session_id = "params_s1"
    agent.reset(session_id, user_profile={})

    # turn=0, top_k=0
    res0 = agent.respond(session_id, "shoes", turn=0, top_k=0)
    _assert_valid_contract_response(res0, top_k=0)
    assert len(res0["recommendations"]) == 0

    # turn=-5, top_k=5
    res1 = agent.respond(session_id, "shoes", turn=-5, top_k=5)
    _assert_valid_contract_response(res1, top_k=5)
    assert len(res1["recommendations"]) <= 5

    # turn=999, top_k=50
    res2 = agent.respond(session_id, "shoes", turn=999, top_k=50)
    _assert_valid_contract_response(res2, top_k=50)


def test_retriever_failure_never_raises() -> None:
    """Crashed or disconnected retriever degrades gracefully to 0 candidates without raising."""
    class CrashingRetriever(Retriever):
        name = "crashed_db"

        def is_available(self) -> bool:
            return True

        def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
            raise RuntimeError("Database connection timed out")

    agent = NeeShopsAgent(retriever=CrashingRetriever())
    agent.reset("retriever_crash_s1", user_profile={})

    res = agent.respond("retriever_crash_s1", "running shoes", turn=1, top_k=10)
    assert isinstance(res["message"], str)
    assert res["recommendations"] == []
    assert res["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


def test_ranker_failure_never_raises() -> None:
    """Crashed ranker falls back to HeuristicRanker or returns safe empty recs without raising."""
    class CrashingRanker(Ranker):
        name = "crashing_ranker"

        def is_available(self) -> bool:
            return True

        def rank(self, candidates, catalog_lookup, state, top_k):
            raise ConnectionError("503 LLM service unavailable")

    class DummyRetriever(Retriever):
        name = "dummy"

        def search(self, query: str, state, top_k: int) -> list[Candidate]:
            return [Candidate(parent_asin=f"B00{i}", score=1.0, source="dummy") for i in range(1, 8)]

    agent = NeeShopsAgent(retriever=DummyRetriever(), ranker=CrashingRanker())
    agent.reset("ranker_crash_s1", user_profile={})

    res = agent.respond("ranker_crash_s1", "shoes", turn=1, top_k=5)
    assert isinstance(res["message"], str)
    # Succeeded via fallback to HeuristicRanker
    assert len(res["recommendations"]) == 5
    assert res["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}
