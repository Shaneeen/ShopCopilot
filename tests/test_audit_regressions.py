"""Regressions for the audit's measured failure shapes (2026-08 fresh-run):

- false size from contractions/possessives ("I'm" → m, "Women's" → s)
- false budget from incidental numbers ("2 wearing ways" + "around your neck")
- wildcard-reply boilerplate reinterpreted as a category ("laundry bag")
- every opener routing as Buying ("I'm looking for X, but I'm still exploring")
- override leaving cross-field soft preferences active
- clarification re-asking "other" right after a no-preference answer
- ranker truncation deciding eligibility before feature scoring
- multi-query fusion bypassing the configured route source weights
- brand extraction depending on process hash seed
"""
from copy import deepcopy

from neeshops.agent import NeeShopsAgent
from neeshops.config.settings import load_strategy
from neeshops.conversation.clarification import ClarificationEngine
from neeshops.conversation.constraints import extract_constraints
from neeshops.conversation.intent import detect_route
from neeshops.conversation.state import StateManager
from neeshops.models.session import NO_PREFERENCE, ConversationState, Turn
from neeshops.ranking.deterministic import ConstraintAwareRanker
from neeshops.retrieval.base import Candidate, Retriever
from neeshops.retrieval.hybrid import HybridRetriever


# -- extraction ---------------------------------------------------------------


def test_openers_no_false_size_from_contraction():
    updates = extract_constraints("I'm looking for ankle boots, but I'm still exploring.")
    assert "size" not in updates
    assert "boots" in updates["category"]


def test_no_size_from_possessive_in_wildcard_reply():
    updates = extract_constraints("For that, what matters is: Women's.", slot="other")
    assert "size" not in updates


def test_explicit_size_contexts_still_extract():
    assert extract_constraints("I need a size 9 waterproof jacket")["size"] == "9"
    assert extract_constraints("I want size m shoes")["size"] == "m"
    assert extract_constraints("a medium backpack please")["size"] == "medium"


def test_no_budget_from_incidental_numbers():
    updates = extract_constraints(
        "This scarf has 2 wearing ways - you can wrap it around your neck."
    )
    assert "budget" not in updates
    assert "budget" not in extract_constraints("I carry it around town")


def test_budget_still_extracted_from_explicit_phrases():
    assert extract_constraints("I need shoes under $120")["budget"] == 120.0
    assert extract_constraints("my budget is up to $120")["budget"] == 120.0
    assert extract_constraints("budget around $27.99")["budget"] == 27.99
    assert extract_constraints("I need shoes under 80")["budget"] == 80.0
    assert extract_constraints("a budget of 50 works")["budget"] == 50.0


def test_wildcard_reply_does_not_reclassify_category():
    updates = extract_constraints(
        "For that, what matters is: laundry bag.", slot="other"
    )
    assert "category" not in updates
    assert updates["feature"] == "laundry bag"


def test_wildcard_reply_parses_its_fragments():
    updates = extract_constraints(
        "For that, what matters is: cotton; color: black.", slot="other"
    )
    assert updates["material"] == "cotton"
    assert updates["color"] == "black"


def test_brand_multi_mention_deterministic():
    for _ in range(3):
        updates = extract_constraints("I like adidas shoes, not nike")
        assert updates["brand"] == "adidas"


# -- routing ------------------------------------------------------------------


def test_still_exploring_opener_routes_browsing():
    message = "I'm looking for ankle boots, but I'm still exploring."
    assert detect_route(message, previous_route=None, constraint_count=0) == "browsing"


def test_buying_openers_still_route_buying():
    assert (
        detect_route(
            "I'm looking for boots. A key requirement is: leather.",
            previous_route=None,
            constraint_count=0,
        )
        == "buying"
    )
    assert (
        detect_route(
            "I'm looking for boots. A key requirement is: under $80.",
            previous_route=None,
            constraint_count=0,
        )
        == "buying"
    )


# -- override transition ------------------------------------------------------


def test_override_records_turn_keeps_card_values():
    """Measured on the 200-session panel: clearing the disclaimed soft
    fields on the override turn LOWERED override HitRate 0.80 → 0.67 —
    the card's soft values describe the SAME target product, so they stay.
    The override is recorded (override_turn) and normal per-field override
    semantics apply."""
    sm = StateManager()
    sm.reset("s1", {})
    sm.apply_turn(
        "s1",
        turn=1,
        user_message="I'm looking for boots. waterproof",
        extracted_constraints={
            "category": "boots",
            "color": "black",
            "feature": "waterproof",
            "style": "casual",
        },
        route="buying",
    )
    state = sm.apply_turn(
        "s1",
        turn=2,
        user_message="Actually, ignore my earlier preference. What I need is: leather.",
        extracted_constraints={"material": "leather"},
        route="buying",
    )
    assert state.override_turn == 2
    # Same-target card values survive; the new requirement is applied.
    assert state.constraint_value("category") == "boots"
    assert state.constraint_value("color") == "black"
    assert state.constraint_value("feature") == "waterproof"
    assert state.constraint_value("material") == "leather"


def test_accumulated_query_keeps_history_without_override():
    state = ConversationState(
        session_id="s",
        history=[Turn(turn=1, user_message="waterproof hiking boots")],
    )
    query = NeeShopsAgent._conversation_query(state, "more")
    assert "waterproof" in query


# -- preview state / clarification lag ----------------------------------------


def _bare_agent() -> NeeShopsAgent:
    return NeeShopsAgent(catalog_lookup={})


def test_preview_state_carries_route_and_constraints():
    agent = _bare_agent()
    state = ConversationState(
        session_id="s",
        constraints={"category": "boots", "feature": "waterproof"},
    )
    preview = agent._preview_state(
        state, {"material": "leather"}, route="buying", turn=3
    )
    assert preview.constraints["material"] == "leather"
    assert preview.constraints["category"] == "boots"
    assert preview.route == "buying"
    assert preview.turn == 3


def test_decide_sees_current_turn_no_preference():
    engine = ClarificationEngine()
    candidates = [Candidate(f"A{i}", 1.0, "bm25") for i in range(6)]

    stale_view = ConversationState(session_id="s")  # what decide() used to see
    assert engine.decide(stale_view, candidates, turn=2)["ask_attribute"] == "other"

    fresh_view = ConversationState(session_id="s", constraints={"other": NO_PREFERENCE})
    assert engine.decide(fresh_view, candidates, turn=2)["ask_attribute"] != "other"


# -- ranker eligibility -------------------------------------------------------


def _rank_catalog() -> dict:
    catalog = {}
    for i in range(59):
        catalog[f"FILL{i:02d}"] = {
            "title": f"Filler Clothing Item Number {i}",
            "categories": ["Clothing", "T-Shirts"],
            "price": 10.0 + i,
        }
    catalog["TARGET1"] = {
        "title": "Waterproof Hiking Boots",
        "categories": ["Clothing", "Boots"],
        "price": 20.0,
    }
    return catalog


def _rank_state() -> ConversationState:
    return ConversationState(
        session_id="s", constraints={"category": "boots", "feature": "waterproof"}
    )


def _rank_candidates() -> list[Candidate]:
    candidates = [Candidate(f"FILL{i:02d}", 1.0 - i / 100, "bm25") for i in range(59)]
    candidates.append(Candidate("TARGET1", 0.0, "coverage_pad"))
    return candidates


def _ranker(rerank_limit: int) -> ConstraintAwareRanker:
    strategy = deepcopy(load_strategy())
    strategy["ranking"]["deterministic"]["rerank_limit"] = rerank_limit
    return ConstraintAwareRanker(strategy=strategy, token_index=None)


def test_ranker_scores_full_pool_target_beyond_old_window():
    recs = _ranker(320).rank(_rank_candidates(), _rank_catalog(), _rank_state(), 10)
    assert recs[0].parent_asin == "TARGET1"


def test_ranker_truncation_reintroduces_the_bug():
    recs = _ranker(40).rank(_rank_candidates(), _rank_catalog(), _rank_state(), 10)
    assert "TARGET1" not in [r.parent_asin for r in recs]


# -- multi-query route weights ------------------------------------------------


class _StubRetriever(Retriever):
    name = "stub"

    def __init__(self, available: bool = True) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def search(self, query, state, top_k):
        return [Candidate("STUB1", 1.0, self.name)]


def _hybrid_strategy() -> dict:
    return {
        "retrieval": {
            "strategy": "hybrid",
            "candidate_limit": 50,
            "rrf_k": 60,
            "buying": {"bm25_weight": 0.7, "semantic_weight": 0.3},
            "browsing": {"bm25_weight": 0.3, "semantic_weight": 0.7},
            "multi_query": {
                "enabled": True,
                "weights": {"accumulated": 1.0, "latest": 1.0, "constraints": 1.0},
            },
        }
    }


def test_search_multi_applies_route_source_weights(monkeypatch):
    captured = {}

    def fake_merge_rrf(lists, weights, k=60):
        captured["weights"] = dict(weights)
        return []

    monkeypatch.setattr("neeshops.retrieval.hybrid.merge_rrf", fake_merge_rrf)
    retriever = HybridRetriever(
        bm25=_StubRetriever(),
        semantic=_StubRetriever(available=False),
        strategy=_hybrid_strategy(),
    )
    queries = {"accumulated": "boots", "latest": "leather boots"}

    state = ConversationState(session_id="s", route="buying")
    retriever.search_multi(queries, state, top_k=10)
    assert captured["weights"]["bm25:accumulated"] == 0.7
    assert captured["weights"]["bm25:latest"] == 0.7

    state = ConversationState(session_id="s", route="browsing")
    retriever.search_multi(queries, state, top_k=10)
    assert captured["weights"]["bm25:accumulated"] == 0.3
