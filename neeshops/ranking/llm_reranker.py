"""Guarded semantic reranking with a deterministic heuristic fallback."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from typing import Any, Optional

from neeshops.config.settings import get_settings, load_strategy
from neeshops.models.recommendation import Recommendation
from neeshops.models.session import CONSTRAINT_FIELDS, NO_PREFERENCE, ConversationState
from neeshops.ranking.base import Ranker
from neeshops.ranking.heuristic import HeuristicRanker
from neeshops.ranking.providers import (
    GeminiRankingProvider,
    MalformedProviderResponseError,
    MissingCredentialsError,
    OpenRouterRankingProvider,
    ProviderRequest,
    ProviderResult,
    RankingProvider,
    RankingProviderError,
)
from neeshops.retrieval.base import Candidate

RerankClient = Callable[[dict[str, Any], float], Mapping[str, Any]]


class _CallableProvider(RankingProvider):
    """Compatibility adapter for the Phase 2 injected callable contract."""

    name = "callable"

    def __init__(self, client: RerankClient) -> None:
        self._client = client

    def rerank(
        self, request: ProviderRequest, timeout_seconds: float
    ) -> ProviderResult:
        response = self._client(
            {
                "constraints": dict(request.constraints),
                "products": list(request.candidates),
            },
            timeout_seconds,
        )
        if not isinstance(response, Mapping):
            raise MalformedProviderResponseError("Provider response is not a mapping")
        ordered_ids = response.get("ordered_ids")
        if not isinstance(ordered_ids, list):
            raise MalformedProviderResponseError("ordered_ids is missing or invalid")
        usage = response.get("usage")
        usage = usage if isinstance(usage, Mapping) else {}
        return ProviderResult(
            ordered_ids=ordered_ids,
            prompt_tokens=_nullable_token_count(usage.get("prompt_tokens")),
            completion_tokens=_nullable_token_count(usage.get("completion_tokens")),
        )


class LLMReranker(Ranker):
    """Optionally rerank a heuristic shortlist and fail safely on every error."""

    name = "llm_reranker"

    def __init__(
        self,
        provider: Optional[RankingProvider] = None,
        *,
        client: Optional[RerankClient] = None,
        fallback: Optional[Ranker] = None,
        strategy: Optional[dict[str, Any]] = None,
        enabled: Optional[bool] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        if provider is not None and client is not None:
            raise ValueError("Pass provider or client, not both")

        self._strategy = strategy or load_strategy()
        ranking_cfg = self._strategy["ranking"]
        llm_cfg = ranking_cfg.get("llm", {})
        settings = get_settings()

        default_llm = load_strategy()["ranking"]["llm"]
        env_rerank = os.getenv("NEESHOPS_LLM_RERANK_LIMIT")
        strat_rerank = llm_cfg.get("rerank_limit", default_llm.get("rerank_limit", 30))
        if env_rerank is not None and strat_rerank == default_llm.get(
            "rerank_limit", 30
        ):
            self.top_n_to_rerank = int(env_rerank)
        else:
            self.top_n_to_rerank = int(strat_rerank)
        env_min = os.getenv("NEESHOPS_LLM_MIN_CONSTRAINTS")
        strat_min = llm_cfg.get(
            "minimum_constraints", default_llm.get("minimum_constraints", 2)
        )
        if env_min is not None and strat_min == default_llm.get(
            "minimum_constraints", 2
        ):
            self.minimum_constraints = int(env_min)
        else:
            self.minimum_constraints = int(strat_min)
        if timeout_seconds is not None:
            self.timeout_seconds = float(timeout_seconds)
        else:
            env_to = os.getenv("NEESHOPS_LLM_TIMEOUT_SECONDS")
            strat_to = llm_cfg.get(
                "timeout_seconds", default_llm.get("timeout_seconds", 5)
            )
            if env_to is not None and strat_to == default_llm.get("timeout_seconds", 5):
                self.timeout_seconds = float(env_to)
            else:
                self.timeout_seconds = float(strat_to)
        injected = provider is not None or client is not None
        self.enabled = (
            enabled
            if enabled is not None
            else (True if injected else settings.enable_llm_reranker)
        )
        self._fallback = fallback or HeuristicRanker(strategy=self._strategy)

        if client is not None:
            provider = _CallableProvider(client)
        provider_name = (
            os.getenv(
                "NEESHOPS_LLM_PROVIDER", llm_cfg.get("provider", settings.llm_provider)
            )
            .strip()
            .lower()
        )
        model = os.getenv(
            "NEESHOPS_LLM_MODEL", llm_cfg.get("model", settings.llm_model)
        ).strip()
        if provider is None:
            if provider_name == "openrouter":
                provider = OpenRouterRankingProvider(model=model)
            elif provider_name == "gemini":
                provider = GeminiRankingProvider(model=model)
            elif provider_name == "fake":
                from neeshops.ranking.providers.fake import FakeRankingProvider

                provider = FakeRankingProvider(ordered_ids=[])
        self._provider = provider
        sec_name = (
            os.getenv(
                "NEESHOPS_LLM_SECONDARY_PROVIDER",
                llm_cfg.get(
                    "secondary_provider",
                    getattr(settings, "llm_secondary_provider", "gemini"),
                ),
            )
            .strip()
            .lower()
        )
        sec_model = os.getenv(
            "NEESHOPS_LLM_SECONDARY_MODEL",
            llm_cfg.get(
                "secondary_model",
                getattr(settings, "llm_secondary_model", "gemini-3.7-flash"),
            ),
        ).strip()
        self._secondary_provider: Optional[RankingProvider] = None
        if sec_name and sec_name != provider_name:
            if sec_name == "gemini":
                self._secondary_provider = GeminiRankingProvider(model=sec_model)
            elif sec_name == "openrouter":
                self._secondary_provider = OpenRouterRankingProvider(model=sec_model)
            elif sec_name == "fake":
                from neeshops.ranking.providers.fake import FakeRankingProvider

                self._secondary_provider = FakeRankingProvider(ordered_ids=[])

        self.last_usage: dict[str, Optional[int]] = _unknown_usage()
        self.last_latency_ms = 0.0
        self.last_fallback_reason: Optional[str] = None

    def is_available(self) -> bool:
        return bool(
            self.enabled
            and self._provider is not None
            and self._provider.availability_reason() is None
        )

    def rank(
        self,
        candidates: list[Candidate],
        catalog_lookup: dict[str, Any],
        state: ConversationState,
        top_k: int,
    ) -> list[Recommendation]:
        self._reset_run_metrics()
        if not candidates or top_k <= 0:
            return []

        baseline = self._fallback.rank(
            candidates, catalog_lookup, state, top_k=len(candidates)
        )
        if not self.enabled:
            return baseline[:top_k]
        if self._meaningful_constraint_count(state) < self.minimum_constraints:
            return baseline[:top_k]
        if len(baseline) < 2:
            return baseline[:top_k]
        if self._provider is None:
            return self._fallback_result("provider_error", baseline, top_k)
        unavailable_reason = self._provider.availability_reason()
        if unavailable_reason:
            return self._fallback_result(unavailable_reason, baseline, top_k)

        shortlist = self._unique_recommendations(baseline)[: self.top_n_to_rerank]
        if len(shortlist) < 2:
            return baseline[:top_k]
        shortlist_by_id = {item.parent_asin: item for item in shortlist}
        request = self._build_request(shortlist, catalog_lookup, state)

        started = time.perf_counter()
        result: Optional[ProviderResult] = None
        last_reason: Optional[str] = None
        for prov in [self._provider, self._secondary_provider]:
            if prov is None:
                continue
            avail = prov.availability_reason()
            if avail:
                if last_reason is None:
                    last_reason = avail
                continue
            try:
                cand = prov.rerank(request, self.timeout_seconds)
                if not isinstance(cand, ProviderResult):
                    raise MalformedProviderResponseError("Provider returned wrong type")
                valid = self._valid_ordered_ids(cand.ordered_ids, shortlist_by_id)
                if not valid:
                    last_reason = "invalid_provider_result"
                    continue
                result = cand
                break
            except RankingProviderError as exc:
                last_reason = getattr(exc, "reason", "provider_error")
                continue
            except Exception:
                last_reason = "provider_error"
                continue
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        if result is None:
            return self._fallback_result(
                last_reason or "provider_error", baseline, top_k, preserve_metrics=True
            )
        self.last_usage = {
            "prompt_tokens": _nullable_token_count(result.prompt_tokens),
            "completion_tokens": _nullable_token_count(result.completion_tokens),
        }
        ordered_ids = self._valid_ordered_ids(result.ordered_ids, shortlist_by_id)

        seen = set(ordered_ids)
        ordered_ids.extend(
            item.parent_asin for item in shortlist if item.parent_asin not in seen
        )
        seen = set(ordered_ids)
        unique_baseline = self._unique_recommendations(baseline)
        ordered_ids.extend(
            item.parent_asin for item in unique_baseline if item.parent_asin not in seen
        )
        baseline_by_id = {item.parent_asin: item for item in unique_baseline}
        return [baseline_by_id[parent_asin] for parent_asin in ordered_ids[:top_k]]

    def _reset_run_metrics(self) -> None:
        self.last_usage = _unknown_usage()
        self.last_latency_ms = 0.0
        self.last_fallback_reason = None

    def _fallback_result(
        self,
        reason: str,
        baseline: list[Recommendation],
        top_k: int,
        *,
        preserve_metrics: bool = False,
    ) -> list[Recommendation]:
        self.last_fallback_reason = reason
        if not preserve_metrics:
            self.last_usage = _unknown_usage()
            self.last_latency_ms = 0.0
        return baseline[:top_k]

    @staticmethod
    def _meaningful_constraint_count(state: ConversationState) -> int:
        count = 0
        for field in CONSTRAINT_FIELDS:
            value = state.constraints.get(field)
            if value is None or value == NO_PREFERENCE:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, tuple, set, dict)) and not value:
                continue
            count += 1
        return count

    @staticmethod
    def _unique_recommendations(
        recommendations: list[Recommendation],
    ) -> list[Recommendation]:
        unique: list[Recommendation] = []
        seen: set[str] = set()
        for item in recommendations:
            if item.parent_asin and item.parent_asin not in seen:
                unique.append(item)
                seen.add(item.parent_asin)
        return unique

    @staticmethod
    def _valid_ordered_ids(
        raw_ids: Any, shortlist_by_id: dict[str, Recommendation]
    ) -> list[str]:
        if not isinstance(raw_ids, list):
            return []
        valid: list[str] = []
        seen: set[str] = set()
        for parent_asin in raw_ids:
            if (
                isinstance(parent_asin, str)
                and bool(parent_asin.strip())
                and parent_asin in shortlist_by_id
                and parent_asin not in seen
            ):
                valid.append(parent_asin)
                seen.add(parent_asin)
        return valid

    @staticmethod
    def _build_request(
        shortlist: list[Recommendation],
        catalog_lookup: dict[str, Any],
        state: ConversationState,
    ) -> ProviderRequest:
        candidates: list[dict[str, Any]] = []
        for item in shortlist:
            row = catalog_lookup.get(item.parent_asin, {})
            price = row.get("price")
            candidates.append(
                {
                    "parent_asin": item.parent_asin,
                    "title": str(row.get("title", ""))[:200],
                    "price": price if isinstance(price, (int, float)) else None,
                    "categories": _string_list(
                        row.get("categories"), limit=5, text_limit=80
                    ),
                    "features": _string_list(
                        row.get("features"), limit=3, text_limit=160
                    ),
                }
            )
        constraints = {
            field: _compact_constraint(value)
            for field, value in state.constraints.items()
            if field in CONSTRAINT_FIELDS
            and value is not None
            and value != NO_PREFERENCE
        }
        return ProviderRequest(constraints=constraints, candidates=tuple(candidates))


def _string_list(value: Any, *, limit: int, text_limit: int) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    return [str(item)[:text_limit] for item in values[:limit]]


def _compact_constraint(value: Any) -> Any:
    if isinstance(value, str):
        return value[:160]
    if isinstance(value, (list, tuple)):
        return [str(item)[:80] for item in value[:5]]
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)[:160]


def _nullable_token_count(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and value >= 0 else None


def _unknown_usage() -> dict[str, Optional[int]]:
    return {"prompt_tokens": None, "completion_tokens": None}
