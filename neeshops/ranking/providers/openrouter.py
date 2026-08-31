"""OpenRouter adapter — text-model chat completions for candidate reranking."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

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


class OpenRouterRankingResponse(BaseModel):
    ordered_ids: list[str]


class OpenRouterRankingProvider(RankingProvider):
    name = "openrouter"

    def __init__(
        self,
        model: str,
        *,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        http_client: Optional[Any] = None,
        client_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._endpoint = endpoint or os.getenv(
            "OPENROUTER_API_BASE",
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self._http_client = http_client
        self._client_factory = client_factory

    def availability_reason(self) -> Optional[str]:
        key = (
            self._api_key
            or os.getenv("OPENROUTER_API_KEY", "").strip()
            or get_settings().openrouter_api_key
        )
        if not key:
            return "missing_credentials"
        return None

    def rerank(
        self, request: ProviderRequest, timeout_seconds: float
    ) -> ProviderResult:
        if self.availability_reason():
            raise MissingCredentialsError("OpenRouter credentials are unavailable")
        try:
            raw = self._call_api(request, timeout_seconds)
            parsed = self._parse_response(raw)
            usage = raw.get("usage") if isinstance(raw, dict) else None
            return ProviderResult(
                ordered_ids=parsed.ordered_ids,
                prompt_tokens=_tok(usage, "prompt_tokens") if usage else None,
                completion_tokens=_tok(usage, "completion_tokens") if usage else None,
            )
        except RankingProviderError:
            raise
        except TimeoutError:
            raise ProviderTimeoutError("OpenRouter request timed out") from None
        except Exception as exc:
            if "timeout" in type(exc).__name__.lower():
                raise ProviderTimeoutError("OpenRouter request timed out") from None
            raise RankingProviderError("OpenRouter provider request failed") from None

    def _call_api(self, request: ProviderRequest, timeout_seconds: float) -> Any:
        if self._http_client is not None:
            return self._http_client.chat_completions(
                model=self.model,
                messages=_messages(request),
                timeout_seconds=timeout_seconds,
            )
        try:
            import requests
        except ImportError:
            raise RankingProviderError("requests is not installed") from None
        key = (
            self._api_key
            or os.getenv("OPENROUTER_API_KEY", "").strip()
            or get_settings().openrouter_api_key
        )
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        ref = os.getenv("OPENROUTER_REFERER", "").strip()
        title = os.getenv("OPENROUTER_TITLE", "ShopCopilot").strip()
        if ref:
            headers["HTTP-Referer"] = ref
        if title:
            headers["X-Title"] = title
        payload = {
            "model": self.model,
            "messages": _messages(request),
            "temperature": 0,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
        }
        # Ranking is a JSON sort — reasoning tokens are pure latency. Default
        # to instruct mode; NEESHOPS_LLM_REASONING=on restores model default.
        if os.getenv("NEESHOPS_LLM_REASONING", "off").strip().lower() != "on":
            payload["reasoning"] = {"enabled": False}
        factory = self._client_factory
        if factory is not None:
            resp = factory(headers, payload, timeout_seconds, self._endpoint)
            return _unwrap_factory_response(resp)
        resp = requests.post(
            self._endpoint,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
        if resp.status_code == 408 or resp.status_code == 504:
            raise ProviderTimeoutError("OpenRouter request timed out")
        if resp.status_code >= 400:
            raise RankingProviderError(f"OpenRouter HTTP {resp.status_code}")
        try:
            return resp.json()
        except Exception:
            raise MalformedProviderResponseError(
                "OpenRouter response was not JSON"
            ) from None

    @staticmethod
    def _parse_response(raw: Any) -> OpenRouterRankingResponse:
        try:
            if isinstance(raw, OpenRouterRankingResponse):
                return raw
            if isinstance(raw, dict) and "ordered_ids" in raw:
                return OpenRouterRankingResponse.model_validate(raw)
            if isinstance(raw, dict) and "choices" in raw:
                choices = raw.get("choices") or []
                if not choices:
                    raise MalformedProviderResponseError(
                        "OpenRouter response had no choices"
                    )
                msg = choices[0].get("message") or {}
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise MalformedProviderResponseError(
                        "OpenRouter response was empty"
                    )
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    raise MalformedProviderResponseError(
                        "OpenRouter content was not JSON"
                    ) from None
                return OpenRouterRankingResponse.model_validate(data)
            if isinstance(raw, str):
                return OpenRouterRankingResponse.model_validate_json(raw)
            raise MalformedProviderResponseError(
                "OpenRouter response missing ordered_ids"
            )
        except ValidationError:
            raise MalformedProviderResponseError(
                "OpenRouter response did not match ordered_ids schema"
            ) from None


def _messages(request: ProviderRequest) -> list[dict[str, str]]:
    instruction = (
        "Rank only the supplied candidate products from best to worst for "
        "the shopper's explicit current requirements. Hard requirements "
        "take precedence over vague preferences. Never invent or return an "
        "ID outside the candidates and do not add scores or explanations. "
        "You may omit uncertain candidates; local ranking will fill them. "
        "Return JSON with key ordered_ids only."
    )
    body = {
        "shopper_intent": dict(request.constraints),
        "candidates": list(request.candidates),
    }
    return [
        {"role": "system", "content": instruction},
        {
            "role": "user",
            "content": json.dumps(body, ensure_ascii=True, sort_keys=True),
        },
    ]


def _tok(usage: Any, key: str) -> Optional[int]:
    v = usage.get(key) if isinstance(usage, dict) else None
    return v if isinstance(v, int) and v >= 0 else None


def _unwrap_factory_response(resp: Any) -> Any:
    if isinstance(resp, dict):
        return resp
    for attr in ("json", "text"):
        fn = getattr(resp, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    return resp
