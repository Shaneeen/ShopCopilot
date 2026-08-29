"""HeuristicRanker returns valid, ordered Recommendations without
fabricating numeric confidence."""
from neeshops.models.session import ConversationState
from neeshops.ranking.heuristic import HeuristicRanker
from neeshops.retrieval.base import Candidate

CATALOG_LOOKUP = {
    "B001": {"title": "Comfort running shoe", "description": "durable comfort fit"},
    "B002": {"title": "Formal leather boot", "description": "office wear"},
}


def test_rank_orders_by_blended_score_and_returns_all_asins():
    candidates = [
        Candidate(parent_asin="B002", score=0.4, source="bm25"),
        Candidate(parent_asin="B001", score=0.9, source="bm25"),
    ]
    state = ConversationState(session_id="s1")
    ranker = HeuristicRanker()

    recs = ranker.rank(candidates, CATALOG_LOOKUP, state, top_k=10)

    assert [r.parent_asin for r in recs] == ["B001", "B002"]
    assert recs[0].reason  # human-readable, never empty
    assert isinstance(recs[0].score, float)


def test_rank_respects_top_k():
    candidates = [Candidate(parent_asin=f"B{i}", score=float(i), source="bm25") for i in range(5)]
    state = ConversationState(session_id="s1")
    recs = HeuristicRanker().rank(candidates, {}, state, top_k=2)
    assert len(recs) == 2


def test_personalization_never_overrides_explicit_low_retrieval_score():
    """A high-scoring retrieval candidate with no profile-tag overlap
    should still rank above a low-scoring one, even if the low one's text
    happens to overlap the profile tags — personalization is a soft boost,
    not a hard override (Track 4 requirement 7)."""
    candidates = [
        Candidate(parent_asin="B002", score=0.1, source="bm25"),  # low retrieval score
        Candidate(parent_asin="B001", score=0.95, source="bm25"),  # high retrieval score
    ]
    lookup = {
        "B001": {"title": "Lightweight fashion sneaker", "description": ""},
        "B002": {"title": "comfort durability fit", "description": "comfort durability fit"},
    }
    state = ConversationState(session_id="s1")
    state.user_profile.preference_tags = ["comfort", "durability", "fit"]

    recs = HeuristicRanker().rank(candidates, lookup, state, top_k=10)

    assert recs[0].parent_asin == "B001"


def test_ranker_base_defaults():
    from neeshops.ranking.base import Ranker

    class MinimalRanker(Ranker):
        def rank(self, candidates, catalog_lookup, state, top_k):
            return []

    ranker = MinimalRanker()
    assert ranker.is_available() is True
    assert ranker.get_usage() == {"prompt_tokens": 0, "completion_tokens": 0}


def test_llm_reranker_disabled_raises_not_implemented():
    import pytest
    from neeshops.ranking.llm_reranker import LLMReranker

    reranker = LLMReranker()
    assert reranker.is_available() is False
    assert reranker.get_usage() == {"prompt_tokens": 0, "completion_tokens": 0}

    with pytest.raises(NotImplementedError):
        reranker.rank([], {}, ConversationState(session_id="s1"), top_k=10)


def test_ranker_usage_passthrough_in_agent():
    from starter.agent import Agent
    from neeshops.agent import NeeShopsAgent
    from neeshops.models.recommendation import Recommendation
    from neeshops.ranking.base import Ranker
    from neeshops.retrieval.base import Candidate, Retriever

    class MockLLMRanker(Ranker):
        name = "mock_llm"

        def is_available(self) -> bool:
            return True

        def get_usage(self) -> dict[str, int]:
            return {"prompt_tokens": 120, "completion_tokens": 45}

        def rank(self, candidates, catalog_lookup, state, top_k):
            return [
                Recommendation(
                    parent_asin=c.parent_asin,
                    score=c.score,
                    reason="Ranked by Mock LLM",
                    source="mock_llm",
                )
                for c in candidates[:top_k]
            ]

    class DummyRetriever(Retriever):
        name = "dummy"

        def search(self, query: str, state, top_k: int) -> list[Candidate]:
            return [Candidate(parent_asin=f"B00{i}", score=1.0, source="dummy") for i in range(1, 8)]

    agent = NeeShopsAgent(retriever=DummyRetriever(), ranker=MockLLMRanker())
    agent.reset("usage_s1", user_profile={})
    res = agent.respond("usage_s1", "running shoes", turn=1, top_k=5)

    assert res["usage"] == {"prompt_tokens": 120, "completion_tokens": 45}
    assert len(res["recommendations"]) == 5
    assert res["recommendations"][0]["reason"] == "Ranked by Mock LLM"


def test_ranker_unavailable_falls_back_to_heuristic():
    from neeshops.agent import NeeShopsAgent
    from neeshops.ranking.base import Ranker
    from neeshops.retrieval.base import Candidate, Retriever

    class UnavailableRanker(Ranker):
        name = "unavailable_custom"

        def is_available(self) -> bool:
            return False

        def rank(self, candidates, catalog_lookup, state, top_k):
            raise RuntimeError("Should not be called if unavailable")

    class DummyRetriever(Retriever):
        name = "dummy"

        def search(self, query: str, state, top_k: int) -> list[Candidate]:
            return [Candidate(parent_asin=f"B00{i}", score=1.0, source="dummy") for i in range(1, 8)]

    agent = NeeShopsAgent(retriever=DummyRetriever(), ranker=UnavailableRanker())
    agent.reset("unavail_s1", user_profile={})
    res = agent.respond("unavail_s1", "running shoes", turn=1, top_k=3)

    assert len(res["recommendations"]) == 3
    assert res["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}
    assert res["recommendations"][0]["parent_asin"] == "B001"
    assert res["recommendations"][0]["reason"]  # fallback generated heuristic reason


def test_ranker_exception_falls_back_to_heuristic():
    from neeshops.agent import NeeShopsAgent
    from neeshops.ranking.base import Ranker
    from neeshops.retrieval.base import Candidate, Retriever

    class CrashingRanker(Ranker):
        name = "crashing_ranker"

        def is_available(self) -> bool:
            return True

        def rank(self, candidates, catalog_lookup, state, top_k):
            raise ConnectionError("LLM API timeout / connection error")

    class DummyRetriever(Retriever):
        name = "dummy"

        def search(self, query: str, state, top_k: int) -> list[Candidate]:
            return [Candidate(parent_asin=f"B00{i}", score=float(i), source="dummy") for i in range(1, 8)]

    agent = NeeShopsAgent(retriever=DummyRetriever(), ranker=CrashingRanker())
    agent.reset("crash_s1", user_profile={})
    res = agent.respond("crash_s1", "shoes", turn=1, top_k=2)

    assert len(res["recommendations"]) == 2
    assert res["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


def test_ranker_tuple_return_passthrough():
    from neeshops.agent import NeeShopsAgent
    from neeshops.models.recommendation import Recommendation
    from neeshops.ranking.base import Ranker
    from neeshops.retrieval.base import Candidate, Retriever

    class TupleRanker(Ranker):
        name = "tuple_ranker"

        def is_available(self) -> bool:
            return True

        def rank(self, candidates, catalog_lookup, state, top_k):
            recs = [
                Recommendation(
                    parent_asin=c.parent_asin, score=c.score, reason="tuple reason"
                )
                for c in candidates[:top_k]
            ]
            return recs, {"prompt_tokens": 55, "completion_tokens": 22}

    class DummyRetriever(Retriever):
        name = "dummy"

        def search(self, query: str, state, top_k: int) -> list[Candidate]:
            return [Candidate(parent_asin=f"B00{i}", score=1.0, source="dummy") for i in range(1, 8)]

    agent = NeeShopsAgent(retriever=DummyRetriever(), ranker=TupleRanker())
    agent.reset("tuple_s1", user_profile={})
    res = agent.respond("tuple_s1", "shoes", turn=1, top_k=5)

    assert res["usage"] == {"prompt_tokens": 55, "completion_tokens": 22}
    assert res["recommendations"][0]["reason"] == "tuple reason"



def test_build_ranker_strategy_flag_and_availability():
    from unittest.mock import patch
    from neeshops.agent import _build_ranker
    from neeshops.ranking.heuristic import HeuristicRanker
    from neeshops.ranking.llm_reranker import LLMReranker

    # Flag off -> HeuristicRanker
    r1 = _build_ranker({"feature_flags": {"enable_llm_reranker": False}, "ranking": {}})
    assert isinstance(r1, HeuristicRanker)

    # Flag on, but is_available is False -> HeuristicRanker
    r2 = _build_ranker(
        {
            "feature_flags": {"enable_llm_reranker": True},
            "ranking": {"rerank_limit": 20},
        }
    )
    assert isinstance(r2, HeuristicRanker)

    # Flag on, is_available is True -> LLMReranker
    with patch.object(LLMReranker, "is_available", return_value=True):
        r3 = _build_ranker(
            {
                "feature_flags": {"enable_llm_reranker": True},
                "ranking": {"rerank_limit": 25},
            }
        )
        assert isinstance(r3, LLMReranker)
        assert r3.top_n_to_rerank == 25


