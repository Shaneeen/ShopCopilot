"""Offline tests for bounded, eligible, fail-soft semantic reranking."""
from __future__ import annotations

import pytest

from neeshops.models.session import NO_PREFERENCE, ConversationState
from neeshops.ranking.llm_reranker import LLMReranker
from neeshops.ranking.providers import (
    FakeRankingProvider,
    MalformedProviderResponseError,
    ProviderRequest,
    ProviderResult,
    ProviderTimeoutError,
    RankingProvider,
)
from neeshops.retrieval.base import Candidate


def _strategy(limit: int = 30, minimum_constraints: int = 2) -> dict:
    return {
        "ranking": {
            "rerank_limit": 40,
            "personalization_weight": 0.15,
            "llm": {
                "provider": "gemini",
                "model": "gemini-3.7-flash",
                "rerank_limit": limit,
                "minimum_constraints": minimum_constraints,
                "timeout_seconds": 5,
            },
        }
    }


def _state(**constraints) -> ConversationState:
    defaults = {"category": "ankle boots", "color": "black"}
    defaults.update(constraints)
    return ConversationState(session_id="synthetic", constraints=defaults)


def _candidates(count: int = 5) -> list[Candidate]:
    # Synthetic P2-like data, not actual retrieval output.
    return [
        Candidate(f"B{i:03}", float(count - i), "bm25+semantic")
        for i in range(count)
    ]


SYNTHETIC_CATALOG = {
    "B000": {
        "title": "Black genuine leather casual ankle boots",
        "price": 89.99,
        "categories": ["Women", "Shoes", "Boots"],
        "features": ["genuine leather", "black", "side zipper"],
    },
    "B001": {
        "title": "Black synthetic Chelsea boots",
        "price": 64.00,
        "categories": ["Women", "Shoes", "Boots"],
        "features": ["synthetic upper", "black"],
    },
    "B002": {
        "title": "Brown leather ankle boots",
        "price": 99.00,
        "categories": ["Women", "Shoes", "Boots"],
        "features": ["genuine leather", "brown"],
    },
    "B003": {
        "title": "Black leather knee-high boots",
        "price": 119.00,
        "categories": ["Women", "Shoes", "Boots"],
        "features": ["leather", "knee high"],
    },
    "B004": {
        "title": "Generic black sneakers",
        "price": 49.00,
        "categories": ["Women", "Shoes", "Sneakers"],
        "features": ["black", "casual"],
    },
}


def test_valid_provider_order_is_used_and_real_usage_is_recorded():
    provider = FakeRankingProvider(
        ["B002", "B000", "B001"], prompt_tokens=12, completion_tokens=4
    )
    ranker = LLMReranker(provider, strategy=_strategy(), enabled=True)

    recs = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 3)

    assert [rec.parent_asin for rec in recs] == ["B002", "B000", "B001"]
    assert ranker.last_usage == {"prompt_tokens": 12, "completion_tokens": 4}
    assert ranker.last_latency_ms >= 0
    assert ranker.last_fallback_reason is None
    assert provider.calls[0][1] == 5.0


def test_disabled_never_calls_provider_and_is_not_an_error():
    provider = FakeRankingProvider(["B003"])
    ranker = LLMReranker(provider, strategy=_strategy(), enabled=False)

    recs = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 3)

    assert [rec.parent_asin for rec in recs] == ["B000", "B001", "B002"]
    assert not provider.calls
    assert ranker.last_fallback_reason is None


@pytest.mark.parametrize(
    "constraints",
    [
        {},
        {"category": "boots"},
        {"category": "boots", "color": NO_PREFERENCE},
        {"category": "", "color": []},
    ],
)
def test_below_constraint_threshold_skips_provider(constraints):
    provider = FakeRankingProvider(["B003"])
    ranker = LLMReranker(provider, strategy=_strategy(), enabled=True)
    state = ConversationState(session_id="s", constraints=constraints)

    ranker.rank(_candidates(), SYNTHETIC_CATALOG, state, 3)

    assert not provider.calls
    assert ranker.last_fallback_reason is None


def test_threshold_reached_makes_provider_eligible():
    provider = FakeRankingProvider(["B003"])
    ranker = LLMReranker(provider, strategy=_strategy(), enabled=True)
    ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 3)
    assert len(provider.calls) == 1


def test_request_is_bounded_heuristically_ordered_and_text_is_truncated():
    provider = FakeRankingProvider(["B003"])
    lookup = {
        "B000": {
            "title": "x" * 500,
            "categories": ["c" * 200] * 8,
            "features": ["y" * 500] * 5,
        }
    }
    ranker = LLMReranker(provider, strategy=_strategy(limit=2), enabled=True)

    ranker.rank(_candidates(), lookup, _state(), 5)

    request = provider.calls[0][0]
    assert [item["parent_asin"] for item in request.candidates] == ["B000", "B001"]
    assert len(request.candidates) == 2
    assert len(request.candidates[0]["title"]) == 200
    assert len(request.candidates[0]["categories"]) == 5
    assert len(request.candidates[0]["categories"][0]) == 80
    assert len(request.candidates[0]["features"]) == 3
    assert len(request.candidates[0]["features"][0]) == 160
    assert "preference_tags" not in request.constraints


def test_unknown_duplicates_and_omissions_are_validated_then_filled():
    provider = FakeRankingProvider(["UNKNOWN", "B002", "B002", "", "B000"])
    ranker = LLMReranker(provider, strategy=_strategy(), enabled=True)

    recs = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 5)

    assert [rec.parent_asin for rec in recs] == ["B002", "B000", "B001", "B003", "B004"]


class _FailingProvider(RankingProvider):
    def __init__(self, error: Exception) -> None:
        self.error = error

    def rerank(self, request: ProviderRequest, timeout_seconds: float) -> ProviderResult:
        raise self.error


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ProviderTimeoutError("timed out"), "timeout"),
        (MalformedProviderResponseError("bad JSON"), "malformed_response"),
        (RuntimeError("authentication or network failure"), "provider_error"),
    ],
)
def test_provider_failures_return_deterministic_heuristic_result(error, reason):
    ranker = LLMReranker(
        _FailingProvider(error), strategy=_strategy(), enabled=True
    )

    first = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 3)
    second = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 3)

    assert [item.parent_asin for item in first] == ["B000", "B001", "B002"]
    assert [item.parent_asin for item in second] == ["B000", "B001", "B002"]
    assert ranker.last_fallback_reason == reason
    assert ranker.last_latency_ms >= 0
    assert ranker.last_usage == {"prompt_tokens": None, "completion_tokens": None}


@pytest.mark.parametrize("ordered_ids", [[], ["UNKNOWN"], ["", "UNKNOWN"]])
def test_zero_valid_ids_is_an_invalid_provider_result(ordered_ids):
    ranker = LLMReranker(
        FakeRankingProvider(ordered_ids), strategy=_strategy(), enabled=True
    )
    recs = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 2)
    assert [item.parent_asin for item in recs] == ["B000", "B001"]
    assert ranker.last_fallback_reason == "invalid_provider_result"


@pytest.mark.parametrize(
    "response",
    [None, {}, {"ordered_ids": None}, {"ordered_ids": "B001"}],
)
def test_legacy_malformed_response_shapes_fail_soft(response):
    ranker = LLMReranker(
        client=lambda payload, timeout: response,
        strategy=_strategy(),
        enabled=True,
    )
    recs = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 2)
    assert [item.parent_asin for item in recs] == ["B000", "B001"]
    assert ranker.last_fallback_reason == "malformed_response"


def test_missing_gemini_key_falls_back_without_import_or_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("NEESHOPS_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("NEESHOPS_ENABLE_LLM_RERANKER", "true")
    from neeshops.config.settings import get_settings

    get_settings.cache_clear()
    try:
        ranker = LLMReranker(strategy=_strategy())
        recs = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 2)
    finally:
        get_settings.cache_clear()

    assert [item.parent_asin for item in recs] == ["B000", "B001"]
    assert ranker.last_fallback_reason == "missing_credentials"


def test_output_contract_respects_top_k_uniqueness_and_candidate_pool():
    pool = _candidates()
    ranker = LLMReranker(
        FakeRankingProvider(["B004", "B004", "UNKNOWN", "B002"]),
        strategy=_strategy(),
        enabled=True,
    )
    recs = ranker.rank(pool, SYNTHETIC_CATALOG, _state(), 3)
    ids = [item.parent_asin for item in recs]
    assert len(ids) == 3
    assert len(ids) == len(set(ids))
    assert set(ids) <= {item.parent_asin for item in pool}


def test_fake_provider_is_deterministic_and_offline():
    provider = FakeRankingProvider(["B003", "B000"])
    ranker = LLMReranker(provider, strategy=_strategy(), enabled=True)
    first = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 4)
    second = ranker.rank(_candidates(), SYNTHETIC_CATALOG, _state(), 4)
    assert [item.parent_asin for item in first] == [item.parent_asin for item in second]
