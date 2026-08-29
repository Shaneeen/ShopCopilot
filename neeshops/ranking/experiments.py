"""Small reproducible harness for comparing interchangeable Rankers."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from neeshops.models.recommendation import Recommendation
from neeshops.models.session import ConversationState
from neeshops.ranking.base import Ranker
from neeshops.retrieval.base import Candidate


class RetrievalOrderRanker(Ranker):
    """R0: preserve first-seen retrieval order without rescoring."""

    name = "r0_retrieval"

    def rank(self, candidates, catalog_lookup, state, top_k):
        if top_k <= 0:
            return []
        out: list[Recommendation] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate.parent_asin and candidate.parent_asin not in seen:
                out.append(Recommendation(
                    parent_asin=candidate.parent_asin,
                    score=candidate.score,
                    reason="Original retrieval order",
                    source=candidate.source,
                ))
                seen.add(candidate.parent_asin)
            if len(out) >= top_k:
                break
        return out


@dataclass(frozen=True)
class RankingExperimentCase:
    case_id: str
    candidates: list[Candidate]
    catalog_lookup: dict[str, dict[str, Any]]
    state: ConversationState
    expected_parent_asin: Optional[str] = None
    synthetic: bool = True


class RankingExperimentHarness:
    def __init__(self) -> None:
        self._strategies: dict[str, tuple[Ranker, Mapping[str, Any]]] = {}

    def register(
        self, name: str, ranker: Ranker, configuration: Optional[Mapping[str, Any]] = None
    ) -> None:
        if not name:
            raise ValueError("Strategy name must be non-empty")
        self._strategies[name] = (ranker, dict(configuration or {}))

    def run(self, case: RankingExperimentCase, *, top_k: int = 10) -> list[dict[str, Any]]:
        result_limit = min(max(top_k, 0), 10)
        original = _first_unique_ids(case.candidates, 10)
        records: list[dict[str, Any]] = []
        for name, (ranker, configuration) in self._strategies.items():
            started = time.perf_counter()
            error: Optional[str] = None
            try:
                ranked = ranker.rank(
                    case.candidates, case.catalog_lookup, case.state, result_limit
                )
            except Exception as exc:  # harness records failures; ranking code still owns fallback
                ranked = []
                error = type(exc).__name__
            latency_ms = (time.perf_counter() - started) * 1000
            ranked_ids = [item.parent_asin for item in ranked]
            target_rank = (
                ranked_ids.index(case.expected_parent_asin) + 1
                if case.expected_parent_asin in ranked_ids
                else None
            )
            records.append({
                "case_id": case.case_id,
                "strategy_name": name,
                "strategy_configuration": dict(configuration),
                "synthetic": case.synthetic,
                "input_candidate_count": len(case.candidates),
                "original_retrieval_top_10": original,
                "ranked_top_10": ranked_ids,
                "latency_ms": latency_ms,
                "fallback": getattr(ranker, "last_fallback_reason", None),
                "error": error,
                "target_rank": target_rank,
                "reciprocal_rank": (1.0 / target_rank) if target_rank else None,
            })
        return records


def _first_unique_ids(candidates: list[Candidate], limit: int) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.parent_asin and candidate.parent_asin not in seen:
            ids.append(candidate.parent_asin)
            seen.add(candidate.parent_asin)
        if len(ids) >= max(limit, 0):
            break
    return ids
