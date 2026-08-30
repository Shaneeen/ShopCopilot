"""Narrow provider contract for optional semantic candidate reranking."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ProviderRequest:
    """Provider-neutral request containing only explicit intent and products."""

    constraints: Mapping[str, Any]
    candidates: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class ProviderResult:
    """The only information the ranking policy accepts from a provider."""

    ordered_ids: list[str]
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class RankingProviderError(Exception):
    """Safe, credential-free provider failure with a stable reason code."""

    reason = "provider_error"


class MissingCredentialsError(RankingProviderError):
    reason = "missing_credentials"


class ProviderTimeoutError(RankingProviderError):
    reason = "timeout"


class MalformedProviderResponseError(RankingProviderError):
    reason = "malformed_response"


class RankingProvider(ABC):
    """A semantic judge that may only reorder supplied candidate IDs."""

    name: str = "provider"

    def availability_reason(self) -> Optional[str]:
        """Return a fallback code when unavailable, otherwise ``None``."""
        return None

    @abstractmethod
    def rerank(
        self, request: ProviderRequest, timeout_seconds: float
    ) -> ProviderResult:
        raise NotImplementedError
