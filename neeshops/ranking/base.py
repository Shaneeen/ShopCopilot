"""Common ranking interface. A Ranker takes retrieval candidates + the
catalog rows they refer to + conversation/personalization signals, and
returns an ordered list of Recommendations with human-readable reasons.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from neeshops.models.recommendation import Recommendation
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate


class Ranker(ABC):
    name: str = "ranker"

    @abstractmethod
    def rank(
        self,
        candidates: list[Candidate],
        catalog_lookup: dict[str, dict[str, Any]],
        state: ConversationState,
        top_k: int,
    ) -> list[Recommendation]:
        raise NotImplementedError
