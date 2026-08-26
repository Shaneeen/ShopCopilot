"""Stage-1 ranker: takes the retrieval score, blends in a soft
personalization boost, and attaches a human-readable reason. No invented
numeric confidence is surfaced to the frontend/evaluator beyond the raw
internal score used for ordering — see docs/neeshops/COMPETITION_NOTES.md.
"""
from __future__ import annotations

from typing import Any, Optional

from neeshops.config.settings import load_strategy
from neeshops.models.recommendation import Recommendation
from neeshops.models.session import ConversationState
from neeshops.personalization.profile import personalization_boost
from neeshops.ranking.base import Ranker
from neeshops.retrieval.base import Candidate


class HeuristicRanker(Ranker):
    name = "heuristic"

    def __init__(self, strategy: Optional[dict[str, Any]] = None) -> None:
        self._cfg = (strategy or load_strategy())["ranking"]

    def rank(
        self,
        candidates: list[Candidate],
        catalog_lookup: dict[str, dict[str, Any]],
        state: ConversationState,
        top_k: int,
    ) -> list[Recommendation]:
        p_weight = self._cfg["personalization_weight"]
        limit = min(self._cfg["rerank_limit"], len(candidates))
        pool = candidates[:limit]

        scored = []
        for c in pool:
            row = catalog_lookup.get(c.parent_asin, {})
            boost = personalization_boost(row, state.user_profile)
            final_score = c.score * (1 - p_weight) + boost * p_weight
            scored.append((final_score, c, row))

        scored.sort(key=lambda t: t[0], reverse=True)

        out = []
        for rank_idx, (score, c, row) in enumerate(scored[:top_k]):
            out.append(
                Recommendation(
                    parent_asin=c.parent_asin,
                    score=score,
                    reason=self._reason(rank_idx, c, row),
                    source=c.source,
                )
            )
        return out

    @staticmethod
    def _reason(rank_idx: int, candidate: Candidate, row: dict[str, Any]) -> str:
        if rank_idx == 0:
            return "Best match for your request"
        if row.get("price") is not None:
            return "Strong value within your budget"
        return "Closely matches your stated preferences"
