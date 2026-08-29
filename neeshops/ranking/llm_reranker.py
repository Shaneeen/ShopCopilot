"""LLM-based reranking — interface stub for Stage 1.

Gated behind `NEESHOPS_ENABLE_LLM_RERANKER` / `enable_llm_reranker`; the
baseline agent must run correctly with this fully disabled (see
neeshops/agent.py, which falls back to HeuristicRanker whenever this
raises NotImplementedError or the flag is off).
"""
from __future__ import annotations

from typing import Any, Optional

from neeshops.config.settings import get_settings
from neeshops.models.recommendation import Recommendation
from neeshops.models.session import ConversationState
from neeshops.ranking.base import Ranker
from neeshops.retrieval.base import Candidate


class LLMReranker(Ranker):
    name = "llm_reranker"

    def __init__(self, top_n_to_rerank: int = 40) -> None:
        self.top_n_to_rerank = top_n_to_rerank
        self.last_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.enable_llm_reranker and settings.llm_api_key)

    def get_usage(self) -> dict[str, int]:
        return dict(self.last_usage)

    def rank(
        self,
        candidates: list[Candidate],
        catalog_lookup: dict[str, Any],
        state: ConversationState,
        top_k: int,
    ) -> list[Recommendation]:
        if not self.is_available():
            raise NotImplementedError(
                "LLMReranker disabled (set NEESHOPS_ENABLE_LLM_RERANKER=true and "
                "LLM_API_KEY to use it). neeshops/agent.py should fall back to "
                "HeuristicRanker instead of calling this directly when disabled."
            )
        # TODO(Workstream 3): prompt the configured LLM_PROVIDER with the
        # top `self.top_n_to_rerank` candidates + user constraints/history,
        # ask for a reordering + short human-readable reason per item,
        # and record token usage in self.last_usage.
        raise NotImplementedError("LLM reranking prompt/parsing not yet implemented.")
