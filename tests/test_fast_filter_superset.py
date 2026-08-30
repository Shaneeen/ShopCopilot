"""P1 fast filter path: token-set membership must agree with the legacy
substring check on realistic (verbatim-token) constraint values, fail open
on unknown ASINs, and never demote a product the legacy path passed."""
from __future__ import annotations

import pytest

from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate
from neeshops.retrieval.filters import _text_satisfies, _tokens_satisfy, apply_filters
from neeshops.retrieval.token_index import TokenIndex

CATALOG = {
    "B001": {
        "parent_asin": "B001",
        "title": "Black Cotton T-Shirt",
        "features": ["Machine Washable", "Imported"],
        "categories": ["Clothing", "Shirts"],
        "details": {"material": "cotton"},
        "description": ["everyday casual tee"],
        "store": "Acme",
        "price": 12.0,
    },
    "B002": {
        "parent_asin": "B002",
        "title": "Red Wool Sweater",
        "features": ["Hand Wash Only"],
        "categories": ["Clothing", "Knitwear"],
        "description": ["warm winter wear"],
        "store": "Zeta",
        "price": 40.0,
    },
    "B003": {
        "parent_asin": "B003",
        "title": "Blue Denim Jacket",
        "features": ["stain resistant coating"],
        "categories": ["Clothing", "Outerwear"],
        "store": "Acme",
        "price": None,  # unparseable price → budget fail-open
    },
}


def test_fast_path_agrees_with_legacy_on_realistic_values():
    index = TokenIndex(CATALOG)
    # Values exactly as the evaluator discloses them (verbatim fragments of
    # the product's own text) — token semantics on both sides.
    values = [
        "cotton",
        "black",
        "machine washable",
        "machine washable; imported",
        "denim",
        "wool",
        "stain resistant",
        "acme",
    ]
    for asin, row in CATALOG.items():
        for value in values:
            assert _tokens_satisfy(value, asin, index) == _text_satisfies(value, row), (
                f"disagreement on {value!r} for {asin}"
            )


def test_fast_path_diverges_only_on_non_word_substrings():
    """Documented semantic difference: substring containment matches stems
    ("wash" ⊂ "washable"); token membership does not. The simulator's
    verbatim-token inputs never exercise this difference."""
    index = TokenIndex(CATALOG)
    assert _text_satisfies("wash", CATALOG["B001"]) is True
    assert _tokens_satisfy("wash", "B001", index) is False


def test_fast_path_fails_open_on_unknown_asin():
    index = TokenIndex(CATALOG)
    assert _tokens_satisfy("cotton", "UNKNOWN", index) is True


def test_fast_path_never_demotes_where_legacy_passed():
    index = TokenIndex(CATALOG)
    state = ConversationState(session_id="s", constraints={"color": "black"})
    candidates = [Candidate(a, 1.0, "bm25") for a in CATALOG]
    legacy = apply_filters(candidates, CATALOG, state)
    fast = apply_filters(candidates, CATALOG, state, token_index=index)
    # Same survivors, same relative order.
    assert [c.parent_asin for c in fast] == [c.parent_asin for c in legacy]


def test_budget_drop_and_category_drop_identical_across_paths():
    index = TokenIndex(CATALOG)
    state = ConversationState(
        session_id="s", constraints={"budget": 15.0, "category": "shirts"}
    )
    candidates = [Candidate(a, 1.0, "bm25") for a in CATALOG]
    legacy = apply_filters(candidates, CATALOG, state)
    fast = apply_filters(candidates, CATALOG, state, token_index=index)
    assert [c.parent_asin for c in fast] == [c.parent_asin for c in legacy]
    assert "B001" in [c.parent_asin for c in fast]  # survives; others drop
