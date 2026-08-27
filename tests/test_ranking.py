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
