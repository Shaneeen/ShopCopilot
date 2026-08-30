"""R2/R3 deterministic rankers built from explicit extracted features."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

from neeshops.config.settings import load_strategy
from neeshops.models.recommendation import Recommendation
from neeshops.models.session import ConversationState
from neeshops.ranking.base import Ranker
from neeshops.ranking.features import ConstraintEvaluation, RankingFeatureExtractor, RankingFeatures
from neeshops.ranking.signals import normalize_scores, reciprocal_rank_fusion
from neeshops.retrieval.base import Candidate


@dataclass(frozen=True)
class RankingDiagnostic:
    parent_asin: str
    features: RankingFeatures
    constraint_evaluation: ConstraintEvaluation
    relevance_score: float
    original_rank: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConstraintAwareRanker(Ranker):
    """R2: rank by violations first, then constraint coverage (IDF-weighted
    — rare tokens decide ties), then weighted local relevance, then
    popularity, with a deterministic asin tie-break."""

    name = "r2_constraint_aware"

    def __init__(
        self,
        strategy: Optional[dict[str, Any]] = None,
        *,
        extractor: Optional[RankingFeatureExtractor] = None,
        token_index: Any = None,
    ) -> None:
        self._strategy = strategy or load_strategy()
        self._cfg = self._strategy["ranking"]["deterministic"]
        rank_cfg = self._strategy["ranking"]
        self._coverage_weight = float(rank_cfg.get("coverage_weight", 2.0))
        self._coverage_salience_weight = float(
            rank_cfg.get("coverage_salience_weight", 0.5)
        )
        self._full_match_bonus = float(rank_cfg.get("full_match_bonus", 0.5))
        # Below this many active constraints, title/feature overlap are
        # near-duplicates of the one constraint coverage already scores
        # (see browsing-regression note in features.py) rather than
        # independent evidence, so their weight is linearly dampened.
        self._overlap_dampening_threshold = int(
            rank_cfg.get("overlap_dampening_threshold", 2)
        )
        self._browsing_popularity_bump = float(
            rank_cfg.get("browsing_popularity_bump", 0.05)
        )
        self._extractor = extractor or RankingFeatureExtractor(
            budget_tolerance=float(self._cfg.get("budget_tolerance", 1.10)),
            token_index=token_index,
        )
        self.last_diagnostics: dict[str, RankingDiagnostic] = {}
        self.last_latency_ms = 0.0

    def rank(
        self,
        candidates: list[Candidate],
        catalog_lookup: dict[str, dict[str, Any]],
        state: ConversationState,
        top_k: int,
    ) -> list[Recommendation]:
        started = time.perf_counter()
        self.last_diagnostics = {}
        if top_k <= 0 or not candidates:
            self.last_latency_ms = (time.perf_counter() - started) * 1000
            return []

        # rerank_limit is a COST cap, not an eligibility filter: it must sit
        # at or above the retrieval candidate_limit so every pool member is
        # scored. Truncating to 40 BEFORE feature scoring silently decided
        # eligibility by pool-insertion order (guarantee tier, then RRF
        # order) — 4 of the 23 measured misses never entered the rerank
        # window despite being in the candidate pool.
        pool = _unique_candidates(candidates)[: int(self._cfg["rerank_limit"])]
        retrieval_signals = self._retrieval_signals(pool)
        scored: list[tuple[int, float, float, float, str, Candidate]] = []
        for original_rank, (candidate, retrieval_signal) in enumerate(
            zip(pool, retrieval_signals), start=1
        ):
            row = catalog_lookup.get(candidate.parent_asin, {})
            features, evaluation = self._extractor.extract(
                candidate,
                row,
                state,
                retrieval_rank=original_rank,
                retrieval_score_normalized=retrieval_signal,
            )
            enabled: Mapping[str, bool] = self._cfg.get("features_enabled", {})
            relevance = self._aggregate(features)
            if (
                state.route == "browsing"
                and self._browsing_popularity_bump
                and enabled.get("popularity", True)
            ):
                relevance += self._browsing_popularity_bump * features.popularity
            self.last_diagnostics[candidate.parent_asin] = RankingDiagnostic(
                candidate.parent_asin, features, evaluation, relevance, original_rank
            )
            # Coverage is also the primary twin tie-breaker in the sort key
            # (not just an _aggregate() summand) — gate it the same way an
            # ablation disables it, so disabling "coverage" truly isolates
            # the remaining enabled features instead of leaving this tier
            # of the ordering unconditionally active.
            sort_coverage = features.coverage if enabled.get("coverage", True) else 0.0
            sort_popularity = features.popularity if enabled.get("popularity", True) else 0.0
            scored.append(
                (
                    features.hard_constraint_violation_count,
                    -sort_coverage,
                    -relevance,
                    -sort_popularity,
                    candidate.parent_asin,
                    candidate,
                )
            )

        scored.sort(key=lambda item: item[:5])
        recommendations = [
            Recommendation(
                parent_asin=candidate.parent_asin,
                score=_ordering_score(violations, negative_relevance),
                reason=self._reason(violations),
                source=candidate.source,
            )
            for violations, _neg_coverage, negative_relevance, _neg_popularity, _asin, candidate in scored[:top_k]
        ]
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        return recommendations

    def _retrieval_signals(self, candidates: list[Candidate]) -> list[float]:
        method = str(self._cfg.get("retrieval_normalization", "raw"))
        return normalize_scores([candidate.score for candidate in candidates], method)

    def _aggregate(self, features: RankingFeatures) -> float:
        weights: Mapping[str, float] = self._cfg["weights"]
        enabled: Mapping[str, bool] = self._cfg.get("features_enabled", {})
        values = {
            "retrieval": features.retrieval_score_normalized,
            "category": features.category_match,
            "title_overlap": features.title_overlap,
            "feature_overlap": features.feature_overlap,
            "color": features.color_match,
            "material": features.material_match,
            "brand": features.brand_match,
            "style": features.style_match,
            "size": features.size_match,
            "budget": features.budget_fit,
            "personalization": features.personalization_boost,
            "inferred": features.inferred_boost,
        }
        # With few active constraints (typically browsing's single generic
        # category), title/feature overlap mostly re-measure that same one
        # constraint via incidental word repetition rather than adding
        # independent evidence, and can otherwise outvote a well-calibrated
        # retrieval score. Scale their weight down toward 0 as the active
        # constraint count drops below the dampening threshold; at or above
        # it they carry their full configured weight.
        overlap_scale = 1.0
        if self._overlap_dampening_threshold > 0:
            overlap_scale = min(
                1.0,
                features.active_constraint_count / self._overlap_dampening_threshold,
            )
        relevance = 0.0
        for name, value in values.items():
            if not enabled.get(name, True):
                continue
            weight = float(weights.get(name, 0.0))
            if name in ("title_overlap", "feature_overlap"):
                weight *= overlap_scale
            relevance += weight * value
        # Coverage × IDF × salience: among partial matches and twins, a hit
        # on a rare token is far more decisive than a hit on a common one.
        # Gated by "coverage"/"full_match_bonus" in features_enabled so an
        # ablation that disables everything but one named feature truly
        # isolates it instead of leaving these terms unconditionally on.
        if enabled.get("coverage", True):
            relevance += self._coverage_weight * features.coverage
            relevance += self._coverage_salience_weight * features.salience
        if enabled.get("full_match_bonus", True) and features.coverage >= 0.999:
            relevance += self._full_match_bonus
        return relevance

    @staticmethod
    def _reason(violations: int) -> str:
        if violations == 0:
            return "Matches the current stated requirements"
        return "Closest available match after explicit requirement checks"


class FusionAwareRanker(ConstraintAwareRanker):
    """R3: R2 with normalized or genuine per-source fused retrieval signal."""

    name = "r3_fusion_aware"

    def __init__(
        self,
        strategy: Optional[dict[str, Any]] = None,
        *,
        source_rankings: Optional[Mapping[str, list[str]]] = None,
        extractor: Optional[RankingFeatureExtractor] = None,
    ) -> None:
        super().__init__(strategy, extractor=extractor)
        self._source_rankings = source_rankings

    def _retrieval_signals(self, candidates: list[Candidate]) -> list[float]:
        method = str(self._cfg.get("fusion_method", "minmax"))
        if method != "rrf":
            return normalize_scores([candidate.score for candidate in candidates], method)
        if not self._source_rankings:
            # Candidate.source labels do not contain source ranks; fall back to
            # deterministic rank normalization rather than inventing fusion.
            return normalize_scores([candidate.score for candidate in candidates], "rank")
        raw = reciprocal_rank_fusion(
            self._source_rankings, k=int(self._cfg.get("rrf_k", 60))
        )
        return normalize_scores([raw.get(candidate.parent_asin, 0.0) for candidate in candidates], "minmax")


def _unique_candidates(candidates: list[Candidate]) -> list[Candidate]:
    unique: list[Candidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.parent_asin and candidate.parent_asin not in seen:
            unique.append(candidate)
            seen.add(candidate.parent_asin)
    return unique


def _ordering_score(violations: int, relevance: float) -> float:
    """Expose a score consistent with the lexicographic ordering key.

    Relevance is compressed below one, so each violation remains a separate
    tier rather than becoming another small weighted penalty.
    """
    non_negative_relevance = max(0.0, relevance)
    bounded_relevance = non_negative_relevance / (1.0 + non_negative_relevance)
    return bounded_relevance - violations
