"""SemanticRetriever + hybrid fallback behaviour (P2 deliverable D3).

Uses a small fixture catalog and a real (tiny) persisted semantic index —
no 50k catalog needed. Every failure mode must degrade to BM25, never
raise and never yield an empty pool.
"""
import json

import pytest

from neeshops.config.settings import Settings
from neeshops.models.session import ConversationState
from neeshops.retrieval import semantic as semantic_module
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.candidate_merge import merge_weighted
from neeshops.retrieval.hybrid import HybridRetriever
from neeshops.retrieval.semantic import SemanticRetriever, build_index

# Disjoint vocabularies per row so similarity assertions stay unambiguous.
FIXTURE_ROWS = [
    {"parent_asin": "B001", "title": "Black Canvas Sneaker", "description": "casual everyday canvas sneaker", "categories": ["shoes"], "brand": "Acme", "price": 45.0},
    {"parent_asin": "B002", "title": "Red Leather Boot", "description": "durable leather boot", "categories": ["shoes"], "brand": "Acme", "price": 90.0},
    {"parent_asin": "B003", "title": "Blue Denim Jacket", "description": "classic denim jacket", "categories": ["outerwear"], "brand": "Zeta", "price": 60.0},
    {"parent_asin": "B004", "title": "Wireless Noise Cancelling Headphones", "description": "over-ear bluetooth headphones", "categories": ["electronics"], "brand": "Pulse", "price": 150.0},
    {"parent_asin": "B005", "title": "Stainless Steel Water Bottle", "description": "insulated water bottle", "categories": ["kitchen"], "brand": "Trail", "price": 25.0},
    {"parent_asin": "B006", "title": "Wool Beanie Hat", "description": "warm winter beanie", "categories": ["accessories"], "brand": "Zeta", "price": 18.0},
]


@pytest.fixture
def catalog_path(tmp_path):
    path = tmp_path / "catalog.jsonl"
    with open(path, "w") as f:
        for row in FIXTURE_ROWS:
            f.write(json.dumps(row) + "\n")
    return path


@pytest.fixture
def index_paths(catalog_path):
    return (
        catalog_path.parent / "semantic.index.npy",
        catalog_path.parent / "semantic.meta.json",
    )


@pytest.fixture
def build(catalog_path, index_paths):
    def _build():
        return build_index(catalog_path, index_paths[0], index_paths[1], dim=64)

    return _build


def configure(monkeypatch, enabled: bool, catalog_path):
    """Hermetic gating: fresh Settings per lookup (get_settings() is
    lru_cached, so env changes alone aren't enough), pointed at the
    fixture catalog so the stale-hash check sees the right file."""

    def _fresh_settings():
        settings = Settings()
        settings.catalog_path = catalog_path
        settings.enable_semantic_retrieval = enabled
        return settings

    monkeypatch.setenv(
        "NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL", "true" if enabled else "false"
    )
    monkeypatch.setattr(semantic_module, "get_settings", _fresh_settings)


def make_state():
    return ConversationState(session_id="s1")


# --- enabled path -------------------------------------------------------


def test_enabled_returns_valid_asins(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    retriever = SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1])

    assert retriever.is_available() is True
    results = retriever.search("black canvas sneaker", make_state(), top_k=5)

    assert results, "expected semantic hits for 'black canvas sneaker'"
    valid_asins = {row["parent_asin"] for row in FIXTURE_ROWS}
    assert all(c.parent_asin in valid_asins for c in results)
    assert all(c.source == "semantic" for c in results)
    assert results[0].parent_asin == "B001"
    assert all(c.score > 0 for c in results)


def test_hybrid_merges_semantic_when_enabled(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    hybrid = HybridRetriever(
        bm25=BM25Retriever(catalog_path=catalog_path),
        semantic=SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1]),
    )

    results = hybrid.search("black canvas sneaker", make_state(), top_k=10)

    assert results
    sources = {c.source for c in results}
    assert "bm25+semantic" in sources, "the shared hit should be merged, not duplicated"
    merged = next(c for c in results if c.source == "bm25+semantic")
    assert merged.parent_asin == "B001"


# --- fallback paths -----------------------------------------------------


def test_disabled_falls_back_to_bm25(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=False, catalog_path=catalog_path)
    semantic = SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1])
    assert semantic.is_available() is False
    assert semantic.search("black canvas sneaker", make_state(), top_k=5) == []

    hybrid = HybridRetriever(
        bm25=BM25Retriever(catalog_path=catalog_path), semantic=semantic
    )
    results = hybrid.search("black canvas sneaker", make_state(), top_k=10)
    assert results, "BM25-only fallback must still return a pool"
    assert all(c.source == "bm25" for c in results)


def test_corrupt_index_falls_back_to_bm25(catalog_path, index_paths, build, monkeypatch):
    build()
    index_paths[0].write_bytes(b"this is not an npy file")
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    semantic = SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1])

    assert semantic.is_available() is False  # must never raise
    assert semantic.search("black canvas sneaker", make_state(), top_k=5) == []

    hybrid = HybridRetriever(
        bm25=BM25Retriever(catalog_path=catalog_path), semantic=semantic
    )
    results = hybrid.search("black canvas sneaker", make_state(), top_k=10)
    assert results
    assert all(c.source == "bm25" for c in results)


def test_corrupt_meta_falls_back(catalog_path, index_paths, build, monkeypatch):
    build()
    index_paths[1].write_text("{not json", encoding="utf-8")
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    semantic = SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1])

    assert semantic.is_available() is False
    assert semantic.search("sneaker", make_state(), top_k=5) == []


def test_missing_index_is_unavailable(catalog_path, monkeypatch):
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    semantic = SemanticRetriever(
        index_path=catalog_path.parent / "nope.npy",
        meta_path=catalog_path.parent / "nope.meta.json",
    )
    assert semantic.is_available() is False
    assert semantic.search("sneaker", make_state(), top_k=5) == []


def test_stale_index_built_for_other_catalog_is_rejected(
    catalog_path, index_paths, build, monkeypatch
):
    build()
    # Catalog changed since the index was built -> stale -> unavailable.
    with open(catalog_path, "a") as f:
        f.write(json.dumps({"parent_asin": "B999", "title": "New Gadget", "price": 5.0}) + "\n")
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    semantic = SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1])

    assert semantic.is_available() is False


# --- edge cases ---------------------------------------------------------


def test_empty_query_returns_empty(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    retriever = SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1])
    assert retriever.search("", make_state(), top_k=5) == []
    assert retriever.search("   ", make_state(), top_k=5) == []


def test_deterministic_search_order(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)

    def _run():
        retriever = SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1])
        return [
            (c.parent_asin, round(c.score, 6), c.source)
            for c in retriever.search("leather boot bottle", make_state(), top_k=6)
        ]

    assert _run() == _run()


def test_rebuild_is_deterministic(tmp_path):
    rows_a = tmp_path / "a"
    rows_b = tmp_path / "b"
    asins = []
    for base in (rows_a, rows_b):
        base.mkdir()
        with open(base / "catalog.jsonl", "w") as f:
            for row in FIXTURE_ROWS:
                f.write(json.dumps(row) + "\n")
        build_index(
            base / "catalog.jsonl",
            base / "semantic.index.npy",
            base / "semantic.meta.json",
            dim=64,
        )
        with open(base / "semantic.meta.json") as f:
            asins.append(json.load(f)["parent_asins"])
    assert asins[0] == asins[1]


def test_merge_weighted_dedups_duplicate_asin():
    from neeshops.retrieval.base import Candidate

    merged = merge_weighted(
        {
            "bm25": [Candidate("B001", 5.0, "bm25"), Candidate("B002", 3.0, "bm25")],
            "semantic": [Candidate("B001", 0.9, "semantic")],
        },
        {"bm25": 0.7, "semantic": 0.3},
    )

    assert len(merged) == 2, "B001 appeared in both lists and must merge once"
    b001 = next(c for c in merged if c.parent_asin == "B001")
    assert b001.source == "bm25+semantic"
    assert [c.parent_asin for c in merged] == ["B001", "B002"]  # sorted by score
