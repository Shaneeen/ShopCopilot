"""Optional real Gemini smoke test; excluded from normal offline pytest."""
from __future__ import annotations

import os

import pytest

from neeshops.models.session import ConversationState
from neeshops.ranking.llm_reranker import LLMReranker
from neeshops.ranking.providers import GeminiRankingProvider
from neeshops.retrieval.base import Candidate


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY is not configured"
)
def test_real_gemini_semantic_rerank_smoke():
    candidates = [
        Candidate("SYN001", 0.9, "bm25+semantic"),
        Candidate("SYN002", 0.8, "semantic"),
        Candidate("SYN003", 0.7, "bm25"),
    ]
    catalog = {
        "SYN001": {"title": "Brown leather ankle boots", "price": 90},
        "SYN002": {"title": "Black leather ankle boots", "price": 100},
        "SYN003": {"title": "Black running sneakers", "price": 70},
    }
    state = ConversationState(
        session_id="gemini-smoke",
        constraints={"category": "ankle boots", "color": "black"},
    )
    strategy = {
        "ranking": {
            "rerank_limit": 40,
            "personalization_weight": 0.15,
            "llm": {"rerank_limit": 3, "minimum_constraints": 2, "timeout_seconds": 5},
        }
    }
    model = os.getenv("NEESHOPS_LLM_MODEL", "gemini-3.7-flash")
    ranker = LLMReranker(
        GeminiRankingProvider(model=model), strategy=strategy, enabled=True
    )

    recommendations = ranker.rank(candidates, catalog, state, top_k=3)
    ids = [item.parent_asin for item in recommendations]

    assert len(ids) == len(set(ids))
    assert set(ids) == {item.parent_asin for item in candidates}
    assert ranker.last_fallback_reason is None
    print({"latency_ms": ranker.last_latency_ms, "usage": ranker.last_usage})
