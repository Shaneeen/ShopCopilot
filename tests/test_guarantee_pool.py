"""P1 guarantee pool: the verbatim-token invariant.

The simulator's constraint values are verbatim tokens from the target's own
text, so the Boolean AND set contains the target by construction. These
tests build constraints from each target's own tokens (exactly what the
evaluator protocol does) and assert the target survives the guarantee tier,
the pool cap, and greedy backoff.
"""
from __future__ import annotations

import json

import pytest

from neeshops.agent import NeeShopsAgent
from neeshops.retrieval.base import Retriever
from neeshops.retrieval.token_index import TokenIndex, index_tokenize


class _NullRetriever(Retriever):
    """Isolates the guarantee tier: no hybrid hits at all."""

    def search(self, query, state, top_k):
        return []

    def search_multi(self, queries, state, top_k):
        return []


def _catalog(n_docs: int = 60) -> dict[str, dict]:
    """Synthetic catalog: every product carries a unique token triple plus
    one common token ("unisex") so over-generality regimes are reachable."""
    rows: dict[str, dict] = {}
    for i in range(n_docs):
        a, b, c = f"feat{i}", f"kind{i}", f"shade{i}"
        rows[f"T{i:03d}"] = {
            "parent_asin": f"T{i:03d}",
            "title": f"{a} {b} with {c} accents",
            "features": [f"made of {a}", f"{c} finish", "unisex style"],
            "categories": ["Clothing"],
            "price": 10.0 + (i % 40),
            "average_rating": 4.0 + (i % 2),
            "rating_number": 100 + i,
        }
    return rows


def _agent(lookup: dict, retrieval_overrides: dict | None = None) -> NeeShopsAgent:
    """Full default strategy (all sections present) with retrieval overrides."""
    from neeshops.config.settings import load_strategy

    strategy = load_strategy()
    if retrieval_overrides:
        strategy["retrieval"].update(retrieval_overrides)
    return NeeShopsAgent(
        retriever=_NullRetriever(),
        catalog_lookup=lookup,
        strategy=strategy,
    )


@pytest.mark.parametrize("target_index", list(range(50)))
def test_target_own_tokens_put_target_in_guarantee_pool(target_index):
    lookup = _catalog()
    target_asin = f"T{target_index:03d}"
    target_row = lookup[target_asin]
    # Constraints verbatim from the target's own text (simulator behavior).
    state_constraints = {
        "feature": f"feat{target_index}",
        "style": f"kind{target_index}",
        "color": f"shade{target_index}",
    }
    agent = _agent(lookup)
    state = agent.state_manager.reset("s")
    state.constraints = dict(state_constraints)

    candidates, info = agent.build_candidates(
        state, "looking for something specific", {}
    )

    assert info["and_set_size"] == 1  # the triple is unique per product
    assert info["over_generality"] is False
    pool_ids = [c.parent_asin for c in candidates]
    assert target_asin in pool_ids
    assert len(pool_ids) <= 200
    assert candidates[0].parent_asin == target_asin  # guarantee tier is front-loaded


def test_garbage_token_triggers_backoff_and_recovers_target():
    lookup = _catalog()
    agent = _agent(lookup)
    index = agent.token_index
    assert index is not None

    groups = [{"feat10"}, {"zzzqqq"}]  # zzzqqq exists in NO document
    ids, dropped = index.and_search_backoff(groups, price_cap=None, min_ids=1)

    assert "T010" in ids
    assert {"zzzqqq"} in dropped


def test_over_generality_flag_when_and_set_exceeds_limit():
    lookup = _catalog()
    agent = _agent(
        lookup,
        retrieval_overrides={
            "guarantee": {"enabled": True, "rerank_floor": 40, "plausible_set_limit": 5}
        },
    )
    state = agent.state_manager.reset("s")
    state.constraints = {"color": "unisex"}  # a token in EVERY product

    _, info = agent.build_candidates(state, "anything", {})

    assert info["over_generality"] is True
    assert info["ids"] == []  # no guarantee tier in this regime


def test_price_gate_uses_budget_tolerance_and_fails_open():
    lookup = _catalog()
    index = TokenIndex(lookup)
    groups = [{"feat0"}]
    assert "T000" in index.and_search_groups(groups, price_cap=10.0 * 1.10)
    assert index.and_search_groups(groups, price_cap=5.0) == []  # T000 costs 10
    # Unparseable prices never drop a doc (fail-open):
    lookup_junk = dict(lookup)
    lookup_junk["T000"] = {**lookup_junk["T000"], "price": "not-a-price"}
    index_junk = TokenIndex(lookup_junk)
    assert "T000" in index_junk.and_search_groups(groups, price_cap=5.0)


def test_pool_capped_at_candidate_limit_with_hybrid_union():
    lookup = _catalog()
    agent = _agent(
        lookup,
        retrieval_overrides={
            "candidate_limit": 25,
            "guarantee": {"enabled": True, "rerank_floor": 40, "plausible_set_limit": 200},
        },
    )
    state = agent.state_manager.reset("s")
    state.constraints = {"color": "unisex"}  # matches everything → padding
    candidates, info = agent.build_candidates(state, "x", {})
    assert len(candidates) <= 25
    assert info["guarantee_ids"] >= 1


def test_index_tokenize_keeps_sizes_and_stems_plurals():
    assert index_tokenize("Water-Resistant Shoes, size XL 10") == [
        "water", "resistant", "shoe", "size", "xl", "10",
    ]


def test_synonym_expansion_widens_group_retrieval_only():
    from neeshops.retrieval import token_index as ti

    lookup = _catalog()
    # An alias token alone finds nothing; the widened group {feat0, alias0}
    # still finds T000. Expansion is retrieval-only — a group, not a filter.
    original = ti.SYNONYMS.get("feat0")
    ti.SYNONYMS["feat0"] = ("alias0",)
    try:
        index = TokenIndex(lookup)
        assert index.and_search(["alias0"]) == []
        assert "T000" in index.and_search_groups([{"feat0", "alias0"}])
    finally:
        if original is None:
            ti.SYNONYMS.pop("feat0", None)
        else:
            ti.SYNONYMS["feat0"] = original