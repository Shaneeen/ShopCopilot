"""Provider adapters for optional semantic reranking."""

from neeshops.ranking.providers.base import (
    MalformedProviderResponseError,
    MissingCredentialsError,
    ProviderRequest,
    ProviderResult,
    ProviderTimeoutError,
    RankingProvider,
    RankingProviderError,
)
from neeshops.ranking.providers.fake import FakeRankingProvider
from neeshops.ranking.providers.gemini import GeminiRankingProvider

__all__ = [
    "FakeRankingProvider",
    "GeminiRankingProvider",
    "MalformedProviderResponseError",
    "MissingCredentialsError",
    "ProviderRequest",
    "ProviderResult",
    "ProviderTimeoutError",
    "RankingProvider",
    "RankingProviderError",
]
