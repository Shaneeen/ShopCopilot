"""Guarded LLM reranking with a deterministic heuristic fallback.

The provider call is injected so ranking policy and validation can be tested
without network access or a provider SDK. The integration owner can adapt an
OpenAI/Anthropic response to the small mapping documented by ``RerankClient``.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any, Optional

from neeshops.config.settings import get_settings, load_strategy
from neeshops.models.recommendation import Recommendation
from neeshops.models.session import ConversationState
from neeshops.ranking.base import Ranker
from neeshops.ranking.heuristic import HeuristicRanker
from neeshops.retrieval.base import Candidate

RerankClient = Callable[[dict[str, Any], float], Mapping[str, Any]]


class LLMReranker(Ranker):
    """Rerank a bounded candidate slice and fail safely to heuristics."""

    name = "llm_reranker"

    def __init__(
        self,
        client: Optional[RerankClient] = None,
        fallback: Optional[Ranker] = None,
        strategy: Optional[dict[str, Any]] = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._strategy = strategy or load_strategy()
        self.top_n_to_rerank = int(self._strategy["ranking"]["rerank_limit"])
        self._client = client
        self._fallback = fallback or HeuristicRanker(strategy=self._strategy)
        self.timeout_seconds = timeout_seconds
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.last_latency_ms = 0.0
        self.last_fallback_reason: Optional[str] = None

    def is_available(self) -> bool:
        if self._client is not None:
            return True
        settings = get_settings()
        return settings.enable_llm_reranker and bool(settings.llm_api_key)

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
        if not self.is_available():
            return self._use_fallback(
                "LLM reranker is disabled or missing credentials",
                candidates, catalog_lookup, state, top_k,
            )
        if self._client is None:
            return self._use_fallback(
                "No provider adapter is configured",
                candidates, catalog_lookup, state, top_k,
            )

        pool = candidates[: self.top_n_to_rerank]
        baseline = self._fallback.rank(pool, catalog_lookup, state, top_k=len(pool))
        baseline_by_id = {item.parent_asin: item for item in baseline}
        payload = self._build_payload(pool, catalog_lookup, state)

        started = time.perf_counter()
        try:
            response = self._client(payload, self.timeout_seconds)
            self.last_latency_ms = (time.perf_counter() - started) * 1000
            ordered_ids = self._valid_ordered_ids(response, baseline_by_id)
            self.last_usage = self._usage_from(response)
            if not ordered_ids:
                return self._use_fallback(
                    "LLM returned no valid candidate IDs",
                    candidates, catalog_lookup, state, top_k,
                    preserve_latency=True,
                )
        except Exception as exc:  # provider/network/timeout/parsing: fail soft
            self.last_latency_ms = (time.perf_counter() - started) * 1000
            return self._use_fallback(
                f"LLM call failed: {type(exc).__name__}",
                candidates, catalog_lookup, state, top_k,
                preserve_latency=True,
            )

        seen = set(ordered_ids)
        ordered_ids.extend(
            item.parent_asin for item in baseline if item.parent_asin not in seen
        )
        return [baseline_by_id[parent_asin] for parent_asin in ordered_ids[:top_k]]

    def _reset_run_metrics(self) -> None:
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.last_latency_ms = 0.0
        self.last_fallback_reason = None

    def _use_fallback(
        self,
        reason: str,
        candidates: list[Candidate],
        catalog_lookup: dict[str, Any],
        state: ConversationState,
        top_k: int,
        preserve_latency: bool = False,
    ) -> list[Recommendation]:
        self.last_fallback_reason = reason
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if not preserve_latency:
            self.last_latency_ms = 0.0
        return self._fallback.rank(candidates, catalog_lookup, state, top_k)

    @staticmethod
    def _valid_ordered_ids(
        response: Mapping[str, Any],
        baseline_by_id: dict[str, Recommendation],
    ) -> list[str]:
        raw_ids = response.get("ordered_ids")
        if not isinstance(raw_ids, list):
            return []
        valid: list[str] = []
        seen: set[str] = set()
        for parent_asin in raw_ids:
            if (
                isinstance(parent_asin, str)
                and parent_asin in baseline_by_id
                and parent_asin not in seen
            ):
                valid.append(parent_asin)
                seen.add(parent_asin)
        return valid

    @staticmethod
    def _usage_from(response: Mapping[str, Any]) -> dict[str, int]:
        usage = response.get("usage", {})
        if not isinstance(usage, Mapping):
            return {"prompt_tokens": 0, "completion_tokens": 0}

        def token_count(name: str) -> int:
            value = usage.get(name, 0)
            return value if isinstance(value, int) and value >= 0 else 0

        return {
            "prompt_tokens": token_count("prompt_tokens"),
            "completion_tokens": token_count("completion_tokens"),
        }

    @staticmethod
    def _build_payload(
        candidates: list[Candidate],
        catalog_lookup: dict[str, Any],
        state: ConversationState,
    ) -> dict[str, Any]:
        products = []
        for candidate in candidates:
            row = catalog_lookup.get(candidate.parent_asin, {})
            features = row.get("features", [])
            if not isinstance(features, list):
                features = [str(features)]
            products.append(
                {
                    "parent_asin": candidate.parent_asin,
                    "title": str(row.get("title", ""))[:200],
                    "features": [str(value)[:160] for value in features[:3]],
                    "retrieval_score": candidate.score,
                    "source": candidate.source,
                }
            )
        return {
            "instruction": (
                "Return JSON with ordered_ids only. Use only parent_asin values "
                "from products; do not add or duplicate IDs."
            ),
            "constraints": dict(state.constraints),
            "preference_tags": list(state.user_profile.preference_tags),
            "products": products,
        }
