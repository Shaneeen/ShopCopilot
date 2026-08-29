"""Common retriever interface. Every retrieval strategy (BM25, semantic,
hybrid) implements this so the agent orchestrator and the hybrid combiner
can treat them interchangeably.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from neeshops.models.session import ConversationState


class Candidate:
    """One retrieval hit before ranking. Deliberately lighter than
    `Recommendation` (no "reason" yet — that's a ranking-stage concept).

    The 3-field constructor is the stable P3 contract. `metadata` is an
    OPTIONAL retrieval-provenance dict, additive and never required
    (default None — ranking code must not depend on it):

        {
            "rank": int,   # final retrieval rank in the returned pool, 1-based
            "bm25":     {"raw_score": float, "rank": int},  # one entry per
            "semantic": {"raw_score": float, "rank": int},  # source that hit it
        }

    `rank` inside a source entry is the position within that retriever's
    own list (1-based), so P3 never has to reconstruct per-source ordering
    from the merged score."""

    __slots__ = ("parent_asin", "score", "source", "metadata")

    def __init__(
        self,
        parent_asin: str,
        score: float,
        source: str,
        metadata: Optional[dict] = None,
    ) -> None:
        self.parent_asin = parent_asin
        self.score = score
        self.source = source
        self.metadata = metadata

    def __repr__(self) -> str:  # pragma: no cover
        return f"Candidate({self.parent_asin!r}, score={self.score:.3f}, source={self.source!r})"


class Retriever(ABC):
    """Interface every retrieval strategy must implement.

    `query` is the constructed search string (see neeshops/agent.py for how
    it's built from the user message + state); `state` is provided so a
    retriever can also look at structured constraints if useful.
    """

    name: str = "retriever"

    @abstractmethod
    def search(
        self,
        query: str,
        state: ConversationState,
        top_k: int,
    ) -> list[Candidate]:
        raise NotImplementedError

    def is_available(self) -> bool:
        """Whether this retriever can run right now (e.g. catalog index
        built, optional dependency installed). Lets the hybrid retriever and
        the agent degrade gracefully instead of crashing."""
        return True
