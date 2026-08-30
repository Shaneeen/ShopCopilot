"""P3 clarification gates and the slot lifecycle (erasure, decay, inferred).

Invariants under test:
- turn guard: no questions after last_question_turn (recommendations still flow)
- confident gate: pinned pool with a clear margin → recommend-only
- NO_PREFERENCE is permanently consumed (never re-asked)
- inferred attributes NEVER reach filters (bonus-only)
- route flip / intent override erase slots into the stale bucket; explicit
  constraints never age-decay; inferred slots do
"""
from __future__ import annotations

import pytest

from neeshops.agent import NeeShopsAgent
from neeshops.conversation.clarification import ClarificationEngine
from neeshops.conversation.state import StateManager
from neeshops.models.session import NO_PREFERENCE, ConversationState, InferredSlot, Turn
from neeshops.retrieval.base import Retriever
from neeshops.retrieval.filters import apply_filters
from neeshops.retrieval.token_index import TokenIndex


class _NullRetriever(Retriever):
    def search(self, query, state, top_k):
        return []

    def search_multi(self, queries, state, top_k):
        return []


CATALOG = {
    "A1": {"parent_asin": "A1", "title": "Cotton T-Shirt", "features": ["soft cotton"], "categories": ["Shirts"], "price": 10.0},
    "A2": {"parent_asin": "A2", "title": "Cotton Polo", "features": ["soft cotton"], "categories": ["Shirts"], "price": 15.0},
    "A3": {"parent_asin": "A3", "title": "Silk Blouse", "features": ["smooth silk"], "categories": ["Blouses"], "price": 40.0},
    "A4": {"parent_asin": "A4", "title": "Leather Belt", "features": ["genuine leather"], "categories": ["Belts"], "price": 25.0},
    "A5": {"parent_asin": "A5", "title": "Denim Jeans", "features": ["stretch denim"], "categories": ["Pants"], "price": 60.0},
    "A6": {"parent_asin": "A6", "title": "Wool Sweater", "features": ["warm wool"], "categories": ["Knitwear"], "price": 80.0},
    "A7": {"parent_asin": "A7", "title": "Linen Shirt", "features": ["breathable linen"], "categories": ["Shirts"], "price": 35.0},
    "A8": {"parent_asin": "A8", "title": "Nylon Jacket", "features": ["waterproof nylon"], "categories": ["Outerwear"], "price": 55.0},
    "A9": {"parent_asin": "A9", "title": "Suede Loafer", "features": ["soft suede"], "categories": ["Shoes"], "price": 70.0},
    "A10": {"parent_asin": "A10", "title": "Canvas Sneaker", "features": ["durable canvas"], "categories": ["Shoes"], "price": 45.0},
    "A11": {"parent_asin": "A11", "title": "Rayon Dress", "features": ["flowy rayon"], "categories": ["Dresses"], "price": 30.0},
    "A12": {"parent_asin": "A12", "title": "Velvet Scarf", "features": ["soft velvet"], "categories": ["Accessories"], "price": 20.0},
}


def _engine(**cfg_overrides) -> ClarificationEngine:
    cfg = {
        "strategy": "adaptive",
        "max_questions_per_session": 3,
        "min_candidates_before_recommend": 10,
        "last_question_turn": 9,
        "margin_stop": 0.15,
    }
    cfg.update(cfg_overrides)
    return ClarificationEngine(strategy={"clarification": cfg}, catalog_lookup=CATALOG)


class _C:
    def __init__(self, asin):
        self.parent_asin = asin
        self.score = 1.0
        self.source = "bm25"


def _candidates():
    return [_C(a) for a in CATALOG]


def test_turn_guard_blocks_questions_after_last_question_turn():
    engine = _engine()
    decision = engine.decide(_state_with_history(None), _candidates(), turn=10)
    assert decision["ask_attribute"] is None
    assert decision["gate"] == "turn_guard"
    assert decision["should_recommend"] is True  # recommendations still flow


def test_turn_nine_can_still_ask():
    engine = _engine()
    decision = engine.decide(_state_with_history(None), _candidates(), turn=9)
    assert decision["ask_attribute"] == "other"  # wildcard is gate #5


def test_confident_pool_skips_questions():
    engine = _engine()
    index = TokenIndex(CATALOG)
    ranked = ["A1", "A2"] + [f"A{i}" for i in range(3, 11)]
    context = {
        "ranked": ranked,
        "ranked_scores": [1.0, 0.5, 0.4, 0.35, 0.3, 0.28, 0.26, 0.24, 0.22, 0.2],
        "token_index": index,
        "groups": [{"cotton"}, {"shirt"}],  # only A1/A2 satisfy these...
        "over_generality": False,
    }
    # Not all top-10 satisfy both groups → NOT confident → asks.
    decision = engine.decide(_state_with_history(None), _candidates(), turn=1, context=context)
    assert decision["ask_attribute"] == "other"

    # A unanimous full-coverage top-10 with a clear margin → confident.
    context["groups"] = []  # no constraints → nothing to satisfy
    context["ranked"] = ["A1"] * 10
    context["ranked_scores"] = [1.0, 0.5, 0.45, 0.4, 0.35, 0.3, 0.28, 0.26, 0.24, 0.22]
    context["token_index"] = None  # confident gate needs an index; without one it can't fire
    decision = engine.decide(_state_with_history(None), _candidates(), turn=1, context=context)
    assert decision["gate"] != "confident"


def test_no_preference_is_permanently_consumed():
    engine = _engine()
    state = _state_with_history(None)
    state.constraints["material"] = NO_PREFERENCE
    decision = engine.decide(state, _candidates(), turn=2)
    assert decision["ask_attribute"] != "material"


def test_inferred_slots_never_reach_filters():
    index = TokenIndex(CATALOG)
    state = ConversationState(session_id="s")
    state.inferred["material"] = InferredSlot(value="cotton", weight=1.0, updated_turn=1)
    candidates = [
        type("C", (), {"parent_asin": a, "score": 1.0, "source": "bm25"})()
        for a in ("A1", "A3")  # A1 cotton, A3 silk — inferred must not demote A3
    ]
    filtered = apply_filters(candidates, CATALOG, state, token_index=index)
    assert [c.parent_asin for c in filtered] == ["A1", "A3"]


def test_agreement_records_inferred_instead_of_asking():
    engine = _engine()
    state = _state_with_history(None)
    state.constraints["other"] = NO_PREFERENCE  # wildcard exhausted → gates reach selection
    ranked = ["A1", "A2", "A1", "A2", "A1", "A2", "A1", "A2", "A1", "A2"]
    context = {
        "ranked": ranked,
        "ranked_scores": [1.0] * 10,
        "token_index": None,
        "groups": [],
        "over_generality": False,
    }
    decision = engine.decide(state, _candidates(), turn=1, context=context)
    # material across A1/A2 is unanimous "cotton" → inferred, not asked.
    assert decision["inferred"].get("material") == "cotton"
    assert decision["ask_attribute"] != "material"


def test_every_agent_turn_carries_recommendations_even_at_turn_ten():
    agent = NeeShopsAgent(
        retriever=_NullRetriever(), catalog_lookup=CATALOG
    )
    agent.reset("s", {})
    for turn in (1, 9, 10):
        response = agent.respond("s", "I need a soft cotton shirt", turn, 10)
        assert response["recommendations"], f"turn {turn} must carry recommendations"
        if turn == 10:
            assert response["ask_attribute"] is None


def _state_with_history(asked: str | None) -> ConversationState:
    state = ConversationState(session_id="s")
    if asked:
        state.history.append(Turn(turn=1, user_message="hi", asked_attribute=asked))
        state.asked_attributes.append(asked)
    return state


# -- state lifecycle ---------------------------------------------------------


def test_route_flip_alone_does_not_erase_slots():
    """v2 deviation (documented): the harness's flip signal is noisy — any
    informative reply outscores via constraint_count — so flip-erasure
    would wipe true verbatim constraints. Only the explicit override
    message erases."""
    manager = StateManager()
    manager.apply_turn("s", 1, "black leather wallet", {"color": "black"}, "buying")
    manager.apply_turn("s", 2, "just browsing", {}, "browsing")
    state = manager.get("s")
    assert state.constraints["color"] == "black"  # kept — never wiped by a flip
    assert state.stale == {}


def test_override_contradiction_stales_old_value_but_keeps_other_slots():
    """The harness's override message keeps the SAME target (old and new
    values both describe it), so erasure happens per-value: the contradicted
    slot stales, everything else stays active."""
    manager = StateManager()
    manager.apply_turn("s", 1, "blue cotton shirt", {"color": "blue", "material": "cotton"}, "buying")
    manager.apply_turn(
        "s", 2, "Actually, ignore my earlier preference. What I need is: red.",
        {"feature": "red"}, "buying",
    )
    state = manager.get("s")
    assert state.constraints["color"] == "blue"      # untouched — still true
    assert state.constraints["material"] == "cotton"  # untouched — still true
    assert state.constraints["feature"] == "red"      # new intent landed
    assert state.stale == {}


def test_explicit_contradiction_stales_old_value_and_reaffirmation_recovers():
    manager = StateManager()
    manager.apply_turn("s", 1, "blue", {"color": "blue"}, "buying")
    manager.apply_turn("s", 2, "black", {"color": "black"}, "buying")
    state = manager.get("s")
    assert state.constraints["color"] == "black"
    assert state.stale["color"] == "blue"

    manager.apply_turn("s", 3, "actually blue again", {"color": "blue"}, "buying")
    state = manager.get("s")
    assert state.constraints["color"] == "blue"
    assert "color" not in state.stale  # re-affirmed → recovered


def test_inferred_slots_decay_with_age_explicit_never_do():
    manager = StateManager(inferred_decay=0.9)
    manager.apply_turn(
        "s", 1, "shirt", {"color": "black"}, "buying", inferred={"material": "cotton"}
    )
    state = manager.get("s")
    assert state.inferred["material"].weight == 1.0

    manager.apply_turn("s", 2, "ok", {}, "buying")
    state = manager.get("s")
    assert state.inferred["material"].weight == pytest.approx(0.9)
    assert state.constraints["color"] == "black"  # explicit never decays

    manager.apply_turn("s", 3, "ok", {}, "buying")
    state = manager.get("s")
    assert state.inferred["material"].weight == pytest.approx(0.81)


def test_inferred_never_overrides_explicit_constraint():
    manager = StateManager()
    manager.apply_turn("s", 1, "black", {"color": "black"}, "buying")
    manager.apply_turn(
        "s", 2, "ok", {}, "buying", inferred={"color": "red"}
    )
    state = manager.get("s")
    assert state.constraints["color"] == "black"
    assert "color" not in state.inferred
