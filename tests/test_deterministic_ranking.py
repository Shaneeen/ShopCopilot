"""R2/R3 unit and contract tests over synthetic P2-like inputs."""

from __future__ import annotations

import math

import pytest

from neeshops.models.session import ConversationState
from neeshops.ranking.deterministic import ConstraintAwareRanker, FusionAwareRanker
from neeshops.ranking.features import MatchStatus, RankingFeatureExtractor
from neeshops.ranking.signals import normalize_scores, reciprocal_rank_fusion
from neeshops.retrieval.base import Candidate
from tests.ranking_fixtures import (
    SYNTHETIC_BOOT_CANDIDATES,
    SYNTHETIC_BOOT_CATALOG,
    boot_state,
    deterministic_strategy,
    profile_state,
)


def _extract(row, state=None):
    return RankingFeatureExtractor().extract(
        Candidate("X", 0.5, "bm25"),
        row,
        state or boot_state(),
        retrieval_rank=1,
        retrieval_score_normalized=0.5,
    )


def test_feature_extraction_matches_category_color_material_and_budget():
    features, evaluation = _extract(SYNTHETIC_BOOT_CATALOG["LEATHER_BLACK"])

    assert features.category_match == 1
    assert features.color_match == 1
    assert features.material_match == 1
    assert features.size_match == 1
    assert features.budget_fit == 1
    assert features.title_overlap > 0
    assert features.feature_overlap > 0
    assert evaluation.hard_violations == ()


def test_explicit_mismatch_and_multiple_violations_are_recorded():
    _, evaluation = _extract(SYNTHETIC_BOOT_CATALOG["SNEAKER"])

    assert evaluation.statuses["category"] is MatchStatus.MISMATCH
    assert evaluation.statuses["material"] is MatchStatus.MISMATCH
    assert set(evaluation.hard_violations) >= {"category", "material"}


def test_missing_metadata_is_unknown_not_a_violation():
    features, evaluation = _extract(SYNTHETIC_BOOT_CATALOG["SPARSE"])

    assert evaluation.statuses["material"] is MatchStatus.UNKNOWN
    assert evaluation.statuses["color"] is MatchStatus.UNKNOWN
    assert features.hard_constraint_violation_count == 0


def test_catalog_feature_text_can_prove_a_match_but_not_a_mismatch():
    matched, matched_evaluation = _extract(
        {
            "title": "Black ankle boot",
            "features": ["Genuine leather upper"],
        }
    )
    unknown, unknown_evaluation = _extract(
        {
            "title": "Black ankle boot",
            "features": ["Comfortable upper"],
        }
    )

    assert matched.material_match == 1
    assert matched_evaluation.statuses["material"] is MatchStatus.MATCH
    assert unknown.material_match == 0
    assert unknown_evaluation.statuses["material"] is MatchStatus.UNKNOWN


def test_soft_style_mismatch_is_not_a_hard_violation():
    row = dict(SYNTHETIC_BOOT_CATALOG["LEATHER_BLACK"], style="formal")
    features, evaluation = _extract(row)

    assert evaluation.statuses["style"] is MatchStatus.UNKNOWN
    assert "style" not in evaluation.hard_violations
    assert features.style_match == 0


def test_highest_retrieval_candidate_loses_when_it_violates_material():
    ranked = ConstraintAwareRanker().rank(
        SYNTHETIC_BOOT_CANDIDATES, SYNTHETIC_BOOT_CATALOG, boot_state(), 5
    )

    assert ranked[0].parent_asin == "LEATHER_BLACK"
    assert [item.parent_asin for item in ranked].index("SYNTHETIC_BLACK") > 0


def test_unknown_metadata_is_not_destroyed_relative_to_explicit_mismatch():
    candidates = [
        Candidate("SYNTHETIC_BLACK", 0.9, "bm25"),
        Candidate("SPARSE", 0.2, "semantic"),
    ]
    ranked = ConstraintAwareRanker().rank(
        candidates, SYNTHETIC_BOOT_CATALOG, boot_state(), 2
    )
    assert [item.parent_asin for item in ranked] == ["SPARSE", "SYNTHETIC_BLACK"]


def test_current_state_only_enforces_intent_override():
    candidates = [
        Candidate("LEATHER_BLACK", 0.9, "bm25"),
        Candidate("LEATHER_BROWN", 0.8, "bm25"),
    ]
    current = boot_state(color="brown")
    ranked = ConstraintAwareRanker().rank(
        candidates, SYNTHETIC_BOOT_CATALOG, current, 2
    )

    assert ranked[0].parent_asin == "LEATHER_BROWN"
    assert "black" not in str(current.constraints.values()).lower()


def test_personalization_can_move_close_candidates():
    catalog = {
        "PLAIN": {"title": "running shoe", "category": "shoes"},
        "COMFORT": {"title": "comfort running shoe", "category": "shoes"},
    }
    candidates = [Candidate("PLAIN", 0.5, "bm25"), Candidate("COMFORT", 0.5, "bm25")]
    state = profile_state("comfort")
    strategy = deterministic_strategy()
    strategy["ranking"]["deterministic"]["weights"]["personalization"] = 0.03
    strategy["ranking"]["deterministic"]["features_enabled"]["personalization"] = True
    ranked = ConstraintAwareRanker(strategy).rank(candidates, catalog, state, 2)
    assert ranked[0].parent_asin == "COMFORT"


def test_personalization_cannot_override_explicit_brand_constraint():
    catalog = {
        "NIKE": {"title": "Nike comfort running shoe", "brand": "Nike"},
        "ADIDAS": {"title": "Adidas running shoe", "brand": "Adidas"},
    }
    candidates = [Candidate("NIKE", 0.99, "bm25"), Candidate("ADIDAS", 0.2, "semantic")]
    state = profile_state("nike", "comfort", brand="Adidas")

    ranked = ConstraintAwareRanker().rank(candidates, catalog, state, 2)
    assert ranked[0].parent_asin == "ADIDAS"


def test_relevance_then_asin_breaks_ties_deterministically():
    catalog = {
        "LOW": {"title": "plain shoe"},
        "HIGH": {"title": "black leather shoe", "features": ["black leather"]},
    }
    state = ConversationState(
        session_id="ties", constraints={"feature": "black leather"}
    )
    candidates = [Candidate("LOW", 0.5, "bm25"), Candidate("HIGH", 0.5, "bm25")]
    ranker = ConstraintAwareRanker()
    assert [r.parent_asin for r in ranker.rank(candidates, catalog, state, 2)] == [
        "HIGH",
        "LOW",
    ]

    # v2 sort contract: violations → coverage → relevance → popularity →
    # parent_asin. Fully tied candidates break by asin (deterministic).
    tied = [Candidate("B", 0.5, "bm25"), Candidate("A", 0.5, "bm25")]
    first = [
        r.parent_asin
        for r in ranker.rank(tied, {}, ConversationState(session_id="s"), 2)
    ]
    second = [
        r.parent_asin
        for r in ranker.rank(tied, {}, ConversationState(session_id="s"), 2)
    ]
    assert first == second == ["A", "B"]


def test_diagnostics_are_inspectable_and_not_public_contract_fields():
    ranker = ConstraintAwareRanker()
    ranked = ranker.rank(
        SYNTHETIC_BOOT_CANDIDATES, SYNTHETIC_BOOT_CATALOG, boot_state(), 1
    )
    diagnostic = ranker.last_diagnostics[ranked[0].parent_asin]
    assert diagnostic.features.material_match == 1
    assert diagnostic.relevance_score >= 0
    assert "features" not in ranked[0].model_dump()
    assert ranker.last_latency_ms >= 0


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("minmax", [0.0, 0.5, 1.0]),
        ("rank", [0.0, 0.5, 1.0]),
        ("raw", [1.0, 2.0, 3.0]),
    ],
)
def test_score_normalization_is_deterministic(method, expected):
    assert normalize_scores([1.0, 2.0, 3.0], method) == expected
    assert normalize_scores([1.0, 2.0, 3.0], method) == expected


def test_normalization_handles_equal_nonfinite_and_empty_scores():
    assert normalize_scores([2.0, 2.0], "minmax") == [1.0, 1.0]
    values = normalize_scores([float("nan"), float("inf"), 1.0], "minmax")
    assert all(math.isfinite(value) for value in values)
    assert normalize_scores([], "rank") == []


def test_rrf_formula_duplicates_and_missing_sources_are_safe():
    fused = reciprocal_rank_fusion(
        {"bm25": ["A", "B", "A"], "semantic": ["B", "C"]}, k=60
    )
    assert fused["A"] == pytest.approx(1 / 61)
    assert fused["B"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["C"] == pytest.approx(1 / 62)
    assert reciprocal_rank_fusion({}, k=60) == {}
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({"bm25": ["A"]}, k=-1)


def test_fusion_ranker_uses_synthetic_independent_source_rankings():
    strategy = deterministic_strategy(fusion_method="rrf")
    candidates = [Candidate("A", 0.9, "bm25"), Candidate("B", 0.8, "semantic")]
    ranker = FusionAwareRanker(
        strategy,
        source_rankings={"bm25": ["B", "A"], "semantic": ["B", "A"]},
    )
    ranked = ranker.rank(candidates, {}, ConversationState(session_id="rrf"), 2)
    assert [item.parent_asin for item in ranked] == ["B", "A"]


def test_fusion_ranker_without_source_ranks_falls_back_to_rank_normalization():
    strategy = deterministic_strategy(fusion_method="rrf")
    candidates = [Candidate("A", 0.9, "bm25+semantic"), Candidate("B", 0.8, "bm25")]
    ranked = FusionAwareRanker(strategy).rank(
        candidates, {}, ConversationState(session_id="rrf-fallback"), 2
    )
    assert [item.parent_asin for item in ranked] == ["A", "B"]


def test_ablation_can_disable_retrieval_and_metadata_features():
    strategy = deterministic_strategy()
    strategy["ranking"]["deterministic"]["weights"]["personalization"] = 0.03
    enabled = strategy["ranking"]["deterministic"]["features_enabled"]
    for key in enabled:
        enabled[key] = key == "personalization"
    catalog = {"A": {"title": "plain"}, "B": {"title": "comfort"}}
    candidates = [Candidate("A", 1.0, "bm25"), Candidate("B", 0.0, "bm25")]
    ranked = ConstraintAwareRanker(strategy).rank(
        candidates, catalog, profile_state("comfort"), 2
    )
    assert ranked[0].parent_asin == "B"


def test_output_contract_top_k_unique_and_candidate_only():
    candidates = SYNTHETIC_BOOT_CANDIDATES + [SYNTHETIC_BOOT_CANDIDATES[1]]
    ranked = ConstraintAwareRanker().rank(
        candidates, SYNTHETIC_BOOT_CATALOG, boot_state(), 3
    )
    ids = [item.parent_asin for item in ranked]
    assert len(ids) == 3
    assert len(ids) == len(set(ids))
    assert set(ids) <= {candidate.parent_asin for candidate in candidates}
    assert [item.score for item in ranked] == sorted(
        [item.score for item in ranked], reverse=True
    )
