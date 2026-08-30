"""P2 coverage × IDF × salience ranking.

Full-coverage items outrank higher-retrieval partial matches; among equal
coverage counts the RARE token decides (IDF tie-break); the ordering is
deterministic down to the asin.
"""
from __future__ import annotations

from neeshops.models.session import ConversationState
from neeshops.ranking.deterministic import ConstraintAwareRanker
from neeshops.retrieval.base import Candidate
from neeshops.retrieval.token_index import TokenIndex


def _ranker(catalog: dict) -> ConstraintAwareRanker:
    return ConstraintAwareRanker(token_index=TokenIndex(catalog))


def test_full_coverage_outranks_higher_retrieval_partial_match():
    catalog = {
        "FULL": {
            "parent_asin": "FULL",
            "title": "black leather wallet",
            "features": ["black leather construction"],
        },
        "PARTIAL": {
            "parent_asin": "PARTIAL",
            "title": "red canvas wallet",
            "features": ["canvas construction"],
        },
    }
    state = ConversationState(
        session_id="s", constraints={"color": "black", "material": "leather"}
    )
    # PARTIAL has 9x the retrieval score but satisfies neither constraint.
    candidates = [
        Candidate("FULL", 0.1, "bm25"),
        Candidate("PARTIAL", 0.9, "bm25"),
    ]
    ranked = _ranker(catalog).rank(candidates, catalog, state, 2)
    assert [r.parent_asin for r in ranked] == ["FULL", "PARTIAL"]


def test_rare_token_match_beats_common_token_match_at_equal_counts():
    # One "zorp" doc (rare) vs "black" in ten docs (common). Each candidate
    # satisfies exactly one of two constraints — coverage differs by IDF.
    catalog = {
        "ZORP": {"parent_asin": "ZORP", "title": "plain item a", "features": ["zorp"]},
    }
    for i in range(10):
        catalog[f"COMMON{i}"] = {
            "parent_asin": f"COMMON{i}",
            "title": "plain filler",
            "features": ["black"],
        }
    catalog["B_HITS_COMMON"] = {
        "parent_asin": "B_HITS_COMMON",
        "title": "plain item b",
        "features": ["black"],
    }
    state = ConversationState(
        session_id="s", constraints={"feature": "zorp", "color": "black"}
    )
    candidates = [
        Candidate("ZORP", 0.5, "bm25"),       # satisfies the rare token
        Candidate("B_HITS_COMMON", 0.5, "bm25"),  # satisfies the common token
    ]
    ranked = _ranker(catalog).rank(candidates, catalog, state, 2)
    assert ranked[0].parent_asin == "ZORP"


def test_popularity_breaks_remaining_ties_then_asin():
    catalog = {
        "AAA": {
            "parent_asin": "AAA",
            "title": "black leather wallet",
            "average_rating": 3.0,
            "rating_number": 10,
        },
        "ZZZ": {
            "parent_asin": "ZZZ",
            "title": "black leather wallet",
            "average_rating": 5.0,
            "rating_number": 1000,
        },
    }
    state = ConversationState(
        session_id="s", constraints={"color": "black", "material": "leather"}
    )
    candidates = [Candidate("ZZZ", 0.5, "bm25"), Candidate("AAA", 0.5, "bm25")]
    ranked = _ranker(catalog).rank(candidates, catalog, state, 2)
    assert [r.parent_asin for r in ranked] == ["ZZZ", "AAA"]  # popularity first


def test_browsing_route_adds_popularity_bump_buying_does_not():
    catalog = {
        "POP": {"parent_asin": "POP", "title": "sneaker", "average_rating": 5.0, "rating_number": 5000},
        "NICHE": {"parent_asin": "NICHE", "title": "sneaker", "average_rating": 3.0, "rating_number": 5},
    }
    candidates = [Candidate("NICHE", 0.9, "bm25"), Candidate("POP", 0.9, "bm25")]
    ranker = _ranker(catalog)
    browsing = ConversationState(session_id="s", route="browsing")
    buying = ConversationState(session_id="s2", route="buying")
    ranker.rank(candidates, catalog, browsing, 2)
    browse_pop = ranker.last_diagnostics["POP"].relevance_score
    browse_niche = ranker.last_diagnostics["NICHE"].relevance_score
    ranker.rank(candidates, catalog, buying, 2)
    buy_pop = ranker.last_diagnostics["POP"].relevance_score
    buy_niche = ranker.last_diagnostics["NICHE"].relevance_score
    # Equal relevance in buying; the popularity bump separates them browsing.
    assert buy_pop == buy_niche
    assert browse_pop > browse_niche
    assert ranker.rank(candidates, catalog, browsing, 2)[0].parent_asin == "POP"


def test_inferred_boost_is_bonus_only_never_a_violation():
    catalog = {
        "INF": {"parent_asin": "INF", "title": "cotton tee", "features": ["soft cotton"]},
        "OTHER": {"parent_asin": "OTHER", "title": "poly tee", "features": ["soft poly"]},
    }
    from neeshops.models.session import InferredSlot

    state = ConversationState(session_id="s")
    state.inferred["material"] = InferredSlot(value="cotton", weight=1.0, updated_turn=1)
    ranker = _ranker(catalog)
    # Equal retrieval: the inferred bonus (never a filter/demotion) is the
    # only differentiator; both stay with zero violations.
    candidates = [Candidate("OTHER", 0.50, "bm25"), Candidate("INF", 0.50, "bm25")]
    ranked = ranker.rank(candidates, catalog, state, 2)
    assert [r.parent_asin for r in ranked] == ["INF", "OTHER"]
