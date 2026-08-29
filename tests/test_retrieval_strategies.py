"""Retrieval provenance (P3 handoff) + strategy switch (P2-A/B/C/D).

Covers: optional Candidate.metadata, provenance stamping in merge_weighted /
merge_rrf / stamp_provenance, the retrieval.strategy knob on
HybridRetriever, its fail-soft fallbacks, and SemanticRetriever.set_strategy.
Uses a small fixture catalog and a real (tiny) persisted semantic index.
"""
import json

import pytest

from neeshops.config.settings import Settings
from neeshops.models.session import ConversationState
from neeshops.retrieval import semantic as semantic_module
from neeshops.retrieval.base import Candidate
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.candidate_merge import merge_rrf, merge_weighted, stamp_provenance
from neeshops.retrieval.hybrid import HybridRetriever
from neeshops.retrieval.semantic import SemanticRetriever, build_index

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
    """Hermetic gating (same pattern as test_semantic_retrieval.py):
    fresh Settings per lookup pointed at the fixture catalog."""

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


def make_strategy(mode: str, candidate_limit: int = 10, rrf_k: int = 60, semantic_flag: bool = True):
    return {
        "retrieval": {
            "candidate_limit": candidate_limit,
            "strategy": mode,
            "rrf_k": rrf_k,
            "buying": {"bm25_weight": 0.7, "semantic_weight": 0.3},
            "browsing": {"bm25_weight": 0.3, "semantic_weight": 0.7},
        },
        "feature_flags": {"enable_semantic_retrieval": semantic_flag},
    }


def make_hybrid(catalog_path, index_paths, mode, **strategy_kw):
    return HybridRetriever(
        bm25=BM25Retriever(catalog_path=catalog_path),
        semantic=SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1]),
        strategy=make_strategy(mode, **strategy_kw),
    )


# --- Candidate metadata contract -----------------------------------------


def test_candidate_metadata_is_optional_and_additive():
    c = Candidate("B001", 0.9, "bm25")
    assert c.metadata is None  # the 3-field P3 contract is untouched
    c2 = Candidate("B001", 0.9, "bm25", metadata={"rank": 1})
    assert c2.metadata == {"rank": 1}


# --- merge_weighted provenance -------------------------------------------


def test_merge_weighted_stamps_provenance():
    merged = merge_weighted(
        {
            "bm25": [Candidate("B001", 5.0, "bm25"), Candidate("B002", 3.0, "bm25")],
            "semantic": [Candidate("B001", 0.9, "semantic")],
        },
        {"bm25": 0.7, "semantic": 0.3},
    )

    b001 = merged[0]
    assert b001.parent_asin == "B001"
    assert b001.source == "bm25+semantic"
    assert b001.metadata["rank"] == 1
    assert b001.metadata["bm25"] == {"raw_score": 5.0, "rank": 1}
    assert b001.metadata["semantic"] == {"raw_score": 0.9, "rank": 1}

    b002 = merged[1]
    assert b002.metadata["rank"] == 2
    assert b002.metadata["bm25"] == {"raw_score": 3.0, "rank": 2}
    assert "semantic" not in b002.metadata


def test_merge_weighted_breaks_exact_ties_deterministically():
    merged = merge_weighted(
        {"bm25": [Candidate("B009", 5.0, "bm25"), Candidate("B001", 5.0, "bm25")]},
        {"bm25": 1.0},
    )
    # Both normalise to the same score -> tie broken by parent_asin asc.
    assert [c.parent_asin for c in merged] == ["B001", "B009"]


# --- merge_rrf (P2-D fused) ------------------------------------------------


def test_merge_rrf_prefers_items_hit_by_both_sources():
    merged = merge_rrf(
        {
            "bm25": [Candidate("B001", 5.0, "bm25"), Candidate("B002", 3.0, "bm25")],
            "semantic": [Candidate("B002", 0.9, "semantic"), Candidate("B003", 0.8, "semantic")],
        },
        {"bm25": 0.7, "semantic": 0.3},
        k=60,
    )

    assert [c.parent_asin for c in merged] == ["B002", "B001", "B003"]
    b002 = merged[0]
    assert b002.source == "bm25+semantic"
    assert b002.metadata["rank"] == 1
    assert b002.metadata["bm25"]["rank"] == 2
    assert b002.metadata["semantic"]["rank"] == 1
    b003 = merged[2]
    assert b003.source == "semantic"
    assert b003.metadata["semantic"]["raw_score"] == pytest.approx(0.8)


def test_merge_rrf_breaks_exact_ties_deterministically():
    merged = merge_rrf(
        {
            "bm25": [Candidate("B009", 5.0, "bm25")],
            "semantic": [Candidate("B001", 0.9, "semantic")],
        },
        {"bm25": 0.5, "semantic": 0.5},
        k=60,
    )
    # Both rank 1 with equal weights -> identical fused score -> asin asc.
    assert [c.parent_asin for c in merged] == ["B001", "B009"]


# --- stamp_provenance (single-source strategies) ---------------------------


def test_stamp_provenance_on_single_source_list():
    cands = [Candidate("B002", 0.5, "bm25"), Candidate("B001", 0.4, "bm25")]
    out = stamp_provenance(cands, "bm25")
    assert out is cands
    assert out[0].metadata == {"rank": 1, "bm25": {"raw_score": 0.5, "rank": 1}}
    assert out[1].metadata == {"rank": 2, "bm25": {"raw_score": 0.4, "rank": 2}}


# --- HybridRetriever strategies --------------------------------------------


def test_hybrid_bm25_only_ignores_available_semantic(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    hybrid = make_hybrid(catalog_path, index_paths, "bm25_only")

    results = hybrid.search("black canvas sneaker", make_state(), 10)

    assert results
    assert all(c.source == "bm25" for c in results)
    assert all("semantic" not in c.metadata for c in results)
    assert all(c.metadata["bm25"]["raw_score"] == pytest.approx(c.score) for c in results)
    assert [c.metadata["rank"] for c in results] == list(range(1, len(results) + 1))


def test_hybrid_semantic_only_ignores_available_bm25(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    hybrid = make_hybrid(catalog_path, index_paths, "semantic_only")

    results = hybrid.search("black canvas sneaker", make_state(), 10)

    assert results
    assert all(c.source == "semantic" for c in results)
    assert all("bm25" not in c.metadata for c in results)
    assert all(c.metadata["semantic"]["raw_score"] == pytest.approx(c.score) for c in results)
    assert results[0].parent_asin == "B001"


def test_hybrid_fused_merges_both_sources(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    hybrid = make_hybrid(catalog_path, index_paths, "fused")

    results = hybrid.search("black canvas sneaker", make_state(), 10)

    assert results
    assert any(c.source == "bm25+semantic" for c in results)
    assert results[0].metadata["rank"] == 1

    def _signature(res):
        return [(c.parent_asin, round(c.score, 9), c.source) for c in res]

    assert _signature(results) == _signature(hybrid.search("black canvas sneaker", make_state(), 10))


def test_hybrid_default_config_is_hybrid_strategy(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    hybrid = HybridRetriever(
        bm25=BM25Retriever(catalog_path=catalog_path),
        semantic=SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1]),
    )

    results = hybrid.search("black canvas sneaker", make_state(), 10)

    assert results
    assert any(c.source == "bm25+semantic" for c in results)
    assert all(c.metadata["rank"] == i + 1 for i, c in enumerate(results))


# --- fail-soft fallbacks -----------------------------------------------------


def test_hybrid_bm25_only_falls_back_to_semantic(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    hybrid = HybridRetriever(
        bm25=BM25Retriever(catalog_path=catalog_path.parent / "missing.jsonl"),
        semantic=SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1]),
        strategy=make_strategy("bm25_only"),
    )

    results = hybrid.search("black canvas sneaker", make_state(), 10)

    assert results, "fallback must never yield an empty pool"
    assert all(c.source == "semantic" for c in results)


def test_hybrid_semantic_only_falls_back_to_bm25(catalog_path, monkeypatch):
    configure(monkeypatch, enabled=False, catalog_path=catalog_path)
    hybrid = HybridRetriever(
        bm25=BM25Retriever(catalog_path=catalog_path),
        semantic=SemanticRetriever(
            index_path=catalog_path.parent / "nope.npy",
            meta_path=catalog_path.parent / "nope.meta.json",
        ),
        strategy=make_strategy("semantic_only", semantic_flag=False),
    )

    results = hybrid.search("black canvas sneaker", make_state(), 10)

    assert results, "fallback must never yield an empty pool"
    assert all(c.source == "bm25" for c in results)


def test_unknown_strategy_falls_back_to_hybrid(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    hybrid = make_hybrid(catalog_path, index_paths, "bogus_mode")

    results = hybrid.search("black canvas sneaker", make_state(), 10)

    assert results
    assert any(c.source == "bm25+semantic" for c in results)


# --- candidate pool depth + strategy injection -------------------------------


def test_candidate_limit_is_respected(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=True, catalog_path=catalog_path)
    hybrid = make_hybrid(
        catalog_path, index_paths, "bm25_only", candidate_limit=2
    )

    results = hybrid.search("black red blue canvas", make_state(), 200)

    assert 0 < len(results) <= 2, "candidate_limit bounds the pool even when top_k is larger"


def test_semantic_set_strategy_enables_without_env_flag(catalog_path, index_paths, build, monkeypatch):
    build()
    configure(monkeypatch, enabled=False, catalog_path=catalog_path)
    semantic = SemanticRetriever(index_path=index_paths[0], meta_path=index_paths[1])
    assert semantic.is_available() is False

    semantic.set_strategy({"feature_flags": {"enable_semantic_retrieval": True}})

    assert semantic.is_available() is True
    results = semantic.search("black canvas sneaker", make_state(), 5)
    assert results and results[0].parent_asin == "B001"
