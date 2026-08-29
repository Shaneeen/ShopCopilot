"""Gemini adapter unit tests; all network behavior is replaced by fakes."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from neeshops.ranking.providers import (
    GeminiRankingProvider,
    MalformedProviderResponseError,
    MissingCredentialsError,
    ProviderRequest,
    ProviderTimeoutError,
    RankingProviderError,
)


REQUEST = ProviderRequest(
    constraints={"category": "ankle boots", "color": "black"},
    candidates=(
        {
            "parent_asin": "B001",
            "title": "Black leather ankle boots",
            "price": 89.99,
            "categories": ["Shoes", "Boots"],
            "features": ["genuine leather", "black"],
        },
        {
            "parent_asin": "B002",
            "title": "Brown ankle boots",
            "price": 79.99,
            "categories": ["Shoes", "Boots"],
            "features": ["brown"],
        },
    ),
)


class _Models:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class _Client:
    def __init__(self, models):
        self.models = models


def _factory(models, observed):
    def create(**kwargs):
        observed.update(kwargs)
        return _Client(models)

    return create


def test_provider_instantiates_with_config_without_calling_network(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    provider = GeminiRankingProvider(model="gemini-test-model")
    assert provider.model == "gemini-test-model"
    assert provider.availability_reason() is None


def test_missing_key_is_handled_before_sdk_or_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    provider = GeminiRankingProvider(model="gemini-test-model")
    assert provider.availability_reason() == "missing_credentials"
    with pytest.raises(MissingCredentialsError):
        provider.rerank(REQUEST, 5)


def test_structured_response_usage_timeout_and_prompt(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    observed = {}
    response = SimpleNamespace(
        parsed={"ordered_ids": ["B001", "B002"]},
        usage_metadata=SimpleNamespace(
            prompt_token_count=21, candidates_token_count=3
        ),
    )
    models = _Models(response=response)
    provider = GeminiRankingProvider(
        model="gemini-test-model",
        client_factory=_factory(models, observed),
    )

    result = provider.rerank(REQUEST, 5)

    assert result.ordered_ids == ["B001", "B002"]
    assert result.prompt_tokens == 21
    assert result.completion_tokens == 3
    assert observed["http_options"].timeout == 5000
    assert "api_key" not in observed  # production Client discovers GEMINI_API_KEY
    call = models.calls[0]
    assert call["model"] == "gemini-test-model"
    assert call["config"].response_mime_type == "application/json"
    assert "Rank only the supplied candidate products" in call["contents"]
    assert "B001" in call["contents"]
    assert "retrieval_score" not in call["contents"]
    assert "preference_tags" not in call["contents"]


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(parsed={"missing": []}, text=None, usage_metadata=None),
        SimpleNamespace(parsed={"ordered_ids": "B001"}, text=None, usage_metadata=None),
        SimpleNamespace(parsed=None, text="", usage_metadata=None),
        SimpleNamespace(parsed=None, text="not-json", usage_metadata=None),
    ],
)
def test_malformed_structured_responses_are_classified(monkeypatch, response):
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    provider = GeminiRankingProvider(
        model="gemini-test-model",
        client_factory=_factory(_Models(response=response), {}),
    )
    with pytest.raises(MalformedProviderResponseError):
        provider.rerank(REQUEST, 5)


def test_timeout_is_classified_without_exposing_exception_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    provider = GeminiRankingProvider(
        model="gemini-test-model",
        client_factory=_factory(_Models(error=TimeoutError("secret detail")), {}),
    )
    with pytest.raises(ProviderTimeoutError, match="timed out") as caught:
        provider.rerank(REQUEST, 5)
    assert "secret detail" not in str(caught.value)


def test_sdk_provider_exception_is_sanitized(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    provider = GeminiRankingProvider(
        model="gemini-test-model",
        client_factory=_factory(_Models(error=RuntimeError("test-placeholder")), {}),
    )
    with pytest.raises(RankingProviderError) as caught:
        provider.rerank(REQUEST, 5)
    assert caught.value.reason == "provider_error"
    assert "test-placeholder" not in str(caught.value)


def test_missing_usage_is_nullable_not_fabricated(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    response = SimpleNamespace(parsed={"ordered_ids": ["B001"]}, usage_metadata=None)
    provider = GeminiRankingProvider(
        model="gemini-test-model",
        client_factory=_factory(_Models(response=response), {}),
    )
    result = provider.rerank(REQUEST, 5)
    assert result.prompt_tokens is None
    assert result.completion_tokens is None
