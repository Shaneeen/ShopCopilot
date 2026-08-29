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

    def is_available(self) -> bool:
        """Return True if this ranker is configured and ready to run."""
        return True

    def get_usage(self) -> dict[str, int]:
        """Return token usage for the last ranking call."""
        return {"prompt_tokens": 0, "completion_tokens": 0}

    @abstractmethod
    def rank(
        self,
        candidates: list[Candidate],
        catalog_lookup: dict[str, dict[str, Any]],
        state: ConversationState,
        top_k: int,
    ) -> list[Recommendation]:
        raise NotImplementedError
