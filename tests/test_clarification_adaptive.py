"""Slot-filling extraction, adaptive clarification, conversation query
accumulation, and the token-based category/text filters."""
import json

from neeshops.agent import NeeShopsAgent
from neeshops.conversation.clarification import ClarificationEngine
from neeshops.conversation.constraints import extract_constraints
from neeshops.models.session import NO_PREFERENCE, ConversationState, Turn
from neeshops.retrieval.filters import apply_filters, category_filter, text_contains_filter


# -- slot-filling -----------------------------------------------------------

def test_slot_fill_parses_material_answer():
    updates = extract_constraints("For that, what matters is: cotton.", slot="material")
    assert updates["material"] == "cotton"


def test_slot_fill_parses_budget_answer():
    updates = extract_constraints("For that, what matters is: budget around $27.99.", slot="budget")
    assert updates["budget"] == 27.99


def test_slot_fill_parses_color_prefix():
    updates = extract_constraints("For that, what matters is: color: black.", slot="color")
    assert updates["color"] == "black"


def test_slot_fill_records_no_preference():
    updates = extract_constraints(
        "I don't have an additional preference for size.", slot="size"
    )
    assert updates["size"] == NO_PREFERENCE


# -- evaluator-shaped openers ------------------------------------------------

def test_opening_message_sets_category_and_material():
    updates = extract_constraints("I'm looking for women shirts. A key requirement is: cotton.")
    assert "shirt" in updates["category"]
    assert updates["material"] == "cotton"


def test_opening_requirement_color_and_budget():
    updates = extract_constraints("I'm looking for earrings. A key requirement is: color: blue.")
    assert updates["color"] == "blue"

    updates = extract_constraints("I'm looking for a watch. A key requirement is: budget around $45.")
    assert updates["budget"] == 45.0


# -- adaptive clarification ---------------------------------------------------

CATALOG = {
    "A1": {"title": "Cotton T-Shirt", "categories": ["Clothing", "Shirts"], "price": 10.0, "store": "Acme"},
    "A2": {"title": "Cotton Polo", "categories": ["Clothing", "Shirts"], "price": 15.0, "store": "Zeta"},
    "A3": {"title": "Silk Blouse", "categories": ["Clothing", "Blouses"], "price": 40.0, "store": "Acme"},
    "A4": {"title": "Leather Belt", "categories": ["Clothing", "Belts"], "price": 25.0, "store": "Rex"},
    "A5": {"title": "Denim Jeans", "categories": ["Clothing", "Pants"], "price": 60.0, "store": "Rex"},
    "A6": {"title": "Wool Sweater", "categories": ["Clothing", "Knitwear"], "price": 80.0, "store": "Rex"},
}


class FakeCandidate:
    def __init__(self, asin: str) -> None:
        self.parent_asin = asin
        self.score = 1.0
        self.source = "bm25"


def _state_with_history(asked: str | None) -> ConversationState:
    state = ConversationState(session_id="s")
    if asked:
        state.history.append(Turn(turn=1, user_message="hi", asked_attribute=asked))
        state.asked_attributes.append(asked)
    return state


def _engine(catalog_lookup, ask_above=3):
    strategy = {
        "clarification": {
            "strategy": "adaptive",
            "max_questions_per_session": 4,
            "min_candidates_before_recommend": 5,
            "ask_if_candidates_above": ask_above,
        }
    }
    return ClarificationEngine(strategy=strategy, catalog_lookup=catalog_lookup)


def test_wildcard_asked_first_with_and_without_catalog():
    """The open "what else matters?" question yields up to two constraints
    of any type per answer, so it goes first regardless of catalog data.
    (v2 gate order: the small-pool gate blocks ALL asks below
    min_candidates_before_recommend, so both parts use a pool large enough
    for any question to fire.)"""
    engine = _engine(CATALOG)
    candidates = [FakeCandidate(a) for a in CATALOG]
    decision = engine.decide(_state_with_history(None), candidates, turn=1)
    assert decision["ask_attribute"] == "other"
    assert decision["question"]

    engine = _engine({})
    decision = engine.decide(
        _state_with_history(None), [FakeCandidate(a) for a in CATALOG], turn=1
    )
    assert decision["ask_attribute"] == "other"


def test_wildcard_cap_stops_asking_other():
    engine = _engine(CATALOG)
    state = _state_with_history(None)
    for turn in (1, 2, 3):
        state.history.append(
            Turn(turn=turn, user_message=f"ans {turn}", asked_attribute="other", informative=True)
        )
        state.asked_attributes.append("other")
    decision = engine.decide(state, [FakeCandidate(a) for a in CATALOG], turn=4)
    assert decision["ask_attribute"] != "other"


def test_entropy_fallback_after_wildcard_exhausted():
    engine = _engine(CATALOG)
    state = _state_with_history(None)
    state.constraints["other"] = NO_PREFERENCE  # wildcard gave nothing left
    state.history.append(Turn(turn=1, user_message="nothing else", asked_attribute="other"))
    state.asked_attributes.append("other")
    decision = engine.decide(state, [FakeCandidate(a) for a in CATALOG], turn=2)
    assert decision["ask_attribute"] in ("material", "color", "budget")


def test_engine_without_lookup_uses_fixed_order():
    engine = _engine({})
    state = _state_with_history(None)
    state.constraints["category"] = NO_PREFERENCE
    state.constraints["other"] = NO_PREFERENCE  # wildcard exhausted
    candidates = [FakeCandidate(a) for a in CATALOG]
    decision = engine.decide(state, candidates, turn=2)
    assert decision["ask_attribute"] == "material"


# -- conversation query accumulation -----------------------------------------

def test_conversation_query_accumulates_history():
    state = ConversationState(session_id="s")
    state.history.append(Turn(turn=1, user_message="I need black sneakers"))
    query = NeeShopsAgent._conversation_query(state, "size 10 please")
    assert "sneakers" in query and "black" in query and "10" in query


def test_conversation_query_dedupes_tokens():
    state = ConversationState(session_id="s")
    state.history.append(Turn(turn=1, user_message="red dress"))
    query = NeeShopsAgent._conversation_query(state, "a red dress")
    assert query.count("red") == 1 and query.count("dress") == 1


# -- filters ------------------------------------------------------------------

def test_category_filter_matches_tokens_not_phrases():
    state = ConversationState(session_id="s", constraints={"category": "dresses special occasion"})
    row = {"categories": ["Clothing", "Dresses", "Special Occasion"]}
    assert category_filter(row, state) is True
    row_other = {"categories": ["Clothing", "Shirts"]}
    assert category_filter(row_other, state) is False


def test_text_filter_multiword_order_independent():
    state = ConversationState(session_id="s", constraints={"feature": "machine wash; imported"})
    row = {"title": "Imported Tee", "features": ["Machine Washable"]}
    assert text_contains_filter("feature")(row, state) is True


def test_apply_filters_fail_open_on_missing_lookup():
    state = ConversationState(session_id="s", constraints={"color": "black"})
    from neeshops.retrieval.base import Candidate

    candidates = [Candidate(parent_asin="UNKNOWN", score=1.0, source="bm25")]
    assert apply_filters(candidates, {}, state) == candidates
