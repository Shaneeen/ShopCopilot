"""Hybrid retrieval router: picks per-route weights from config, calls each
available sub-retriever, and merges results. This is the one retrieval
entry point neeshops/agent.py talks to.
"""
from __future__ import annotations

from typing import Any, Optional

from neeshops.config.settings import load_strategy
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate, Retriever
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.candidate_merge import merge_weighted
from neeshops.retrieval.semantic import SemanticRetriever
from neeshops.utils.logging import log_event


class HybridRetriever(Retriever):
    name = "hybrid"

    def __init__(
        self,
        bm25: Optional[Retriever] = None,
        semantic: Optional[Retriever] = None,
        strategy: Optional[dict[str, Any]] = None,
    ) -> None:
        self.bm25 = bm25 or BM25Retriever()
        self.semantic = semantic or SemanticRetriever()
        self._strategy = strategy or load_strategy()

    def weights_for_route(self, route: Optional[str]) -> dict[str, float]:
        route_key = route if route in ("buying", "browsing") else "browsing"
        route_cfg = self._strategy["retrieval"][route_key]
        return {"bm25": route_cfg["bm25_weight"], "semantic": route_cfg["semantic_weight"]}

    def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
        weights = self.weights_for_route(state.route)
        candidate_limit = self._strategy["retrieval"]["candidate_limit"]

        results: dict[str, list[Candidate]] = {}

        if self.bm25.is_available():
            results["bm25"] = self.bm25.search(query, state, candidate_limit)
        else:
            results["bm25"] = []

        if self.semantic.is_available():
            results["semantic"] = self.semantic.search(query, state, candidate_limit)
        else:
            results["semantic"] = []

        merged = merge_weighted(results, weights)

        log_event(
            "retrieval.hybrid",
            session_id=state.session_id,
            route=state.route,
            weights=weights,
            bm25_count=len(results["bm25"]),
            semantic_count=len(results["semantic"]),
            merged_count=len(merged),
        )
        return merged[:top_k] if top_k else merged
