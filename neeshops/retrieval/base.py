"""Common retriever interface. Every retrieval strategy (BM25, semantic,
hybrid) implements this so the agent orchestrator and the hybrid combiner
can treat them interchangeably.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from neeshops.models.session import ConversationState


class Candidate:
    """One retrieval hit before ranking. Deliberately lighter than
    `Recommendation` (no "reason" yet — that's a ranking-stage concept)."""

    __slots__ = ("parent_asin", "score", "source")

    def __init__(self, parent_asin: str, score: float, source: str) -> None:
        self.parent_asin = parent_asin
        self.score = score
        self.source = source

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
