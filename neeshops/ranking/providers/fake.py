"""Deterministic, offline provider for tests and local development."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Optional

from neeshops.ranking.providers.base import (
    ProviderRequest,
    ProviderResult,
    RankingProvider,
)


class FakeRankingProvider(RankingProvider):
    name = "fake"

    def __init__(
        self,
        ordered_ids: Iterable[str],
        *,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
    ) -> None:
        self._ordered_ids = list(ordered_ids)
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self.calls: list[tuple[ProviderRequest, float]] = []

    def rerank(
        self, request: ProviderRequest, timeout_seconds: float
    ) -> ProviderResult:
        self.calls.append((request, timeout_seconds))
        return ProviderResult(
            ordered_ids=list(self._ordered_ids),
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
        )
