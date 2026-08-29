"""Demote-not-drop filtering: text constraints reorder instead of dropping,
budget tolerates "around $X" caps, and a wrong category can't empty the
pool once it drops below min_pool_keep."""
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate
from neeshops.retrieval.filters import apply_filters, budget_filter


def _c(asin: str, score: float = 1.0) -> Candidate:
    return Candidate(parent_asin=asin, score=score, source="bm25")


LOOKUP = {
    "MATCH": {"title": "black cotton tee", "categories": ["Clothing", "Shirts"]},
    "MISS": {"title": "red nylon jacket", "categories": ["Clothing", "Jackets"]},
    "SPARSE": {"title": "plain tee"},  # never states colour or material
}


def test_text_constraints_demote_instead_of_drop():
    state = ConversationState(
        session_id="s", constraints={"color": "black", "material": "cotton"}
    )
    candidates = [_c("MISS"), _c("SPARSE"), _c("MATCH")]
    out = apply_filters(candidates, LOOKUP, state)
    assert [c.parent_asin for c in out] == ["MATCH", "MISS", "SPARSE"]


def test_nothing_is_dropped_for_soft_constraints():
    state = ConversationState(
        session_id="s", constraints={"color": "black", "material": "cotton"}
    )
    out = apply_filters([_c("MISS"), _c("SPARSE")], LOOKUP, state)
    assert len(out) == 2


def test_budget_still_hard_drops_with_tolerance():
    state = ConversationState(session_id="s", constraints={"budget": 50})
    # tolerance 1.10: "budget around $50" keeps a $54.90 item, drops $56
    assert budget_filter({"price": 54.9}, state) is True
    assert budget_filter({"price": 56.0}, state) is False

    lookup = {
        "CHEAP": {"title": "tee", "price": 20.0},
        "PRICEY": {"title": "jacket", "price": 90.0},
    }
    out = apply_filters([_c("PRICEY"), _c("CHEAP")], lookup, state)
    assert [c.parent_asin for c in out] == ["CHEAP"]


def test_category_falls_back_to_soft_when_pool_would_empty():
    state = ConversationState(session_id="s", constraints={"category": "dresses"})
    candidates = [_c(f"P{i}") for i in range(5)]
    lookup = {
        f"P{i}": {"title": f"shirt {i}", "categories": ["Clothing", "Shirts"]}
        for i in range(5)
    }
    # min_pool_keep=10 > 5 survivors → category counts as a miss only
    out = apply_filters(candidates, lookup, state)
    assert len(out) == 5


def test_category_hard_drops_while_pool_healthy():
    state = ConversationState(session_id="s", constraints={"category": "dresses"})
    candidates = [_c(f"SHIRT{i}") for i in range(11)] + [_c("JACKET")]
    lookup = {
        **{
            f"SHIRT{i}": {"title": f"shirt {i}", "categories": ["Clothing", "Dresses"]}
            for i in range(11)
        },
        "JACKET": {"title": "leather jacket", "categories": ["Clothing", "Jackets"]},
    }
    # 11 of 12 survive the category check (≥ min_pool_keep) → hard drop
    out = apply_filters(candidates, lookup, state)
    assert [c.parent_asin for c in out] == [f"SHIRT{i}" for i in range(11)]


def test_missing_lookup_rows_pass_through():
    state = ConversationState(session_id="s", constraints={"color": "black"})
    candidates = [_c("UNKNOWN")]
    assert apply_filters(candidates, {}, state) == candidates


def test_explicit_filter_list_keeps_hard_drop_semantics():
    from neeshops.retrieval.filters import text_contains_filter

    state = ConversationState(session_id="s", constraints={"color": "black"})
    out = apply_filters(
        [_c("MATCH"), _c("MISS")], LOOKUP, state, filters=[text_contains_filter("color")]
    )
    assert [c.parent_asin for c in out] == ["MATCH"]
