import json, tempfile
from pathlib import Path
from neeshops.models.session import ConversationState
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.filters import apply_filters, budget_filter, category_filter
from neeshops.retrieval.hybrid import HybridRetriever

FIXTURE = [
    {
        "parent_asin": "B001",
        "title": "Black Canvas Sneaker",
        "description": "casual everyday sneaker",
        "categories": ["Shoes"],
        "price": 45.0,
    },
    {
        "parent_asin": "B002",
        "title": "Red Leather Boot",
        "description": "durable leather boot",
        "categories": ["Shoes"],
        "price": 120.0,
    },
    {
        "parent_asin": "B003",
        "title": "Blue Denim Jacket",
        "description": "classic denim jacket",
        "categories": ["Clothing"],
        "price": 35.0,
    },
]


def _catalog(tmp_path, rows=FIXTURE):
    p = tmp_path / "catalog.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_bm25_real_sorting(tmp_path):
    ret = BM25Retriever(catalog_path=_catalog(tmp_path))
    s = ConversationState(session_id="s1")
    res = ret.search("black sneaker", s, top_k=5)
    assert res and res[0].parent_asin == "B001"
    assert all(c.source == "bm25" for c in res)


def test_budget_filter_real(tmp_path):
    s = ConversationState(session_id="s1", constraints={"budget": 50})
    assert budget_filter({"price": 45.0}, s) is True
    assert budget_filter({"price": 120.0}, s) is False
    assert budget_filter({"price": None}, s) is True
    assert budget_filter({"price": "from 12.99"}, s) is True


def test_category_filter_real(tmp_path):
    s = ConversationState(session_id="s1", constraints={"category": "shoes"})
    assert category_filter({"categories": ["Shoes", "Sneakers"]}, s) is True
    assert category_filter({"categories": ["Clothing", "Jackets"]}, s) is False
    assert category_filter({}, s) is True


def test_hybrid_returns_200_limit(tmp_path):
    ret = HybridRetriever(bm25=BM25Retriever(catalog_path=_catalog(tmp_path)))
    s = ConversationState(session_id="s1", route="buying")
    res = ret.search("shoe", s, top_k=200)
    assert len(res) <= 200


def test_apply_filters_sorting(tmp_path):
    from neeshops.retrieval.base import Candidate

    lookup = {r["parent_asin"]: r for r in FIXTURE}
    cands = [
        Candidate("B001", 1.0, "bm25"),
        Candidate("B002", 0.9, "bm25"),
        Candidate("B003", 0.8, "bm25"),
    ]
    s = ConversationState(session_id="s1", constraints={"budget": 50})
    out = apply_filters(cands, lookup, s)
    assert "B002" not in [c.parent_asin for c in out]
    assert "B001" in [c.parent_asin for c in out]
