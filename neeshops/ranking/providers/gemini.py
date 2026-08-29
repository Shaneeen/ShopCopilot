"""Google Gemini adapter for semantic candidate reranking.

The SDK import and all Gemini response details stay in this module. Ranking
policy never handles SDK objects, credentials, or unvalidated response text.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from neeshops.config.settings import get_settings
from neeshops.ranking.providers.base import (
    MalformedProviderResponseError,
    MissingCredentialsError,
    ProviderRequest,
    ProviderResult,
    ProviderTimeoutError,
    RankingProvider,
    RankingProviderError,
)


class GeminiRankingResponse(BaseModel):
    """Minimal structured output requested from Gemini."""

    ordered_ids: list[str]


class GeminiRankingProvider(RankingProvider):
    name = "gemini"

    def __init__(
        self,
        model: str,
        *,
        api_key: Optional[str] = None,
        client_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client_factory = client_factory

    def availability_reason(self) -> Optional[str]:
        configured_key = (
            self._api_key
            or os.getenv("GEMINI_API_KEY", "").strip()
            or get_settings().gemini_api_key
        )
        if not configured_key:
            return "missing_credentials"
        return None

    def rerank(
        self, request: ProviderRequest, timeout_seconds: float
    ) -> ProviderResult:
        if self.availability_reason():
            raise MissingCredentialsError("Gemini credentials are unavailable")

        client = None
        try:
            client, types = self._make_client(timeout_seconds)
            response = client.models.generate_content(
                model=self.model,
                contents=self._prompt(request),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiRankingResponse,
                    temperature=0,
                    max_output_tokens=512,
                ),
            )
            parsed = self._parse_response(response)
            usage = getattr(response, "usage_metadata", None)
            return ProviderResult(
                ordered_ids=parsed.ordered_ids,
                prompt_tokens=self._token_count(usage, "prompt_token_count"),
                completion_tokens=self._completion_token_count(usage),
            )
        except RankingProviderError:
            raise
        except Exception as exc:
            if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
                raise ProviderTimeoutError("Gemini request timed out") from None
            raise RankingProviderError("Gemini provider request failed") from None
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def _make_client(self, timeout_seconds: float) -> tuple[Any, Any]:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RankingProviderError("google-genai is not installed") from None

        factory = self._client_factory or genai.Client
        kwargs: dict[str, Any] = {
            "http_options": types.HttpOptions(timeout=int(timeout_seconds * 1000))
        }
        # Normal production use intentionally omits api_key so Client discovers
        # GEMINI_API_KEY. Explicit injection exists only for controlled tests.
        if self._api_key:
            kwargs["api_key"] = self._api_key
        return factory(**kwargs), types

    @staticmethod
    def _prompt(request: ProviderRequest) -> str:
        instruction = (
            "Rank only the supplied candidate products from best to worst for "
            "the shopper's explicit current requirements. Hard requirements "
            "take precedence over vague preferences. Never invent or return an "
            "ID outside the candidates and do not add scores or explanations. "
            "You may omit uncertain candidates; local ranking will fill them."
        )
        body = {
            "shopper_intent": dict(request.constraints),
            "candidates": list(request.candidates),
        }
        return f"{instruction}\n\n{json.dumps(body, ensure_ascii=True, sort_keys=True)}"

    @staticmethod
    def _parse_response(response: Any) -> GeminiRankingResponse:
        raw = getattr(response, "parsed", None)
        try:
            if isinstance(raw, GeminiRankingResponse):
                return raw
            if raw is not None:
                return GeminiRankingResponse.model_validate(raw)
            text = getattr(response, "text", None)
            if not isinstance(text, str) or not text.strip():
                raise MalformedProviderResponseError("Gemini response was empty")
            return GeminiRankingResponse.model_validate_json(text)
        except (ValidationError, ValueError, TypeError):
            raise MalformedProviderResponseError(
                "Gemini response did not match the ordered_ids schema"
            ) from None

    @staticmethod
    def _token_count(usage: Any, attribute: str) -> Optional[int]:
        value = getattr(usage, attribute, None) if usage is not None else None
        return value if isinstance(value, int) and value >= 0 else None

    @classmethod
    def _completion_token_count(cls, usage: Any) -> Optional[int]:
        # SDK versions have exposed this as candidates_token_count and, more
        # recently, response_token_count. Support either without estimating.
        candidates = cls._token_count(usage, "candidates_token_count")
        if candidates is not None:
            return candidates
        return cls._token_count(usage, "response_token_count")
