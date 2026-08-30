"""BM25Retriever returns valid parent_asin values against a small fixture
catalog (not the real 50k catalog — that's not committed, see data/README.md)."""
import json

import pytest

from neeshops.models.session import ConversationState
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.filters import budget_filter

FIXTURE_ROWS = [
    {"parent_asin": "B001", "title": "Black Canvas Sneaker", "description": "casual everyday sneaker", "category": "shoes", "brand": "Acme", "color": "black", "material": "canvas"},
    {"parent_asin": "B002", "title": "Red Leather Boot", "description": "durable leather boot", "category": "shoes", "brand": "Acme", "color": "red", "material": "leather"},
    {"parent_asin": "B003", "title": "Blue Denim Jacket", "description": "classic denim jacket", "category": "outerwear", "brand": "Zeta", "color": "blue", "material": "denim"},
]


@pytest.fixture
def catalog_path(tmp_path):
    path = tmp_path / "catalog.jsonl"
    with open(path, "w") as f:
        for row in FIXTURE_ROWS:
            f.write(json.dumps(row) + "\n")
    return path


def test_bm25_returns_valid_parent_asins(catalog_path):
    retriever = BM25Retriever(catalog_path=catalog_path)
    state = ConversationState(session_id="s1")

    results = retriever.search("black sneaker", state, top_k=5)

    assert results, "expected at least one match for 'black sneaker'"
    valid_asins = {row["parent_asin"] for row in FIXTURE_ROWS}
    for candidate in results:
        assert candidate.parent_asin in valid_asins
        assert candidate.source == "bm25"


def test_bm25_empty_query_serves_popular_fallback(catalog_path):
    """No usable keywords (fake prompt / empty context) → a stable
    popularity-ranked slice instead of an empty pool, so recommendations
    never go blank and questions drive convergence."""
    retriever = BM25Retriever(catalog_path=catalog_path)
    state = ConversationState(session_id="s1")
    results = retriever.search("", state, top_k=2)
    assert [c.parent_asin for c in results] == ["B001", "B002"]
    assert all(c.source == "popular" for c in results)


def test_bm25_empty_query_fallback_can_be_disabled(catalog_path):
    retriever = BM25Retriever(
        catalog_path=catalog_path,
        strategy={"retrieval": {"empty_query_fallback": False}},
    )
    state = ConversationState(session_id="s1")
    assert retriever.search("", state, top_k=5) == []


def test_bm25_unavailable_without_catalog(tmp_path):
    retriever = BM25Retriever(catalog_path=tmp_path / "missing.jsonl")
    assert retriever.is_available() is False


def test_budget_filter_handles_real_catalog_price_shapes():
    """The official catalog has float prices, missing prices, and a few junk
    string values ('from 12.99', mojibake) — the filter must fail open, not
    raise (regression: TypeError crashed apply_filters on the 50k catalog)."""
    state = ConversationState(session_id="s1", constraints={"budget": 50})
    assert budget_filter({"price": 19.99}, state) is True
    assert budget_filter({"price": 20}, state) is True        # int price
    assert budget_filter({"price": 60.0}, state) is False
    assert budget_filter({"price": None}, state) is True
    assert budget_filter({"price": "19.99"}, state) is True   # numeric string parses
    assert budget_filter({"price": "from 12.99"}, state) is True  # junk -> fail open
    assert budget_filter({"price": "\ufffd"}, state) is True      # mojibake -> fail open
