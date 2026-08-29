"""Hybrid retrieval router: picks a retrieval strategy and per-route weights
from config, calls each available sub-retriever, and merges results. This is
the one retrieval entry point neeshops/agent.py talks to.

Strategies (`retrieval.strategy` in default_strategy.json) — P2 owns
candidate recall, P3 owns reranking; these only change WHICH pool P3 gets:

- "bm25_only"     P2-A keyword only (raw BM25 scores)
- "semantic_only" P2-B dense only (raw cosine scores)
- "hybrid"        P2-C current default: min-max normalise + weighted sum
- "fused"         P2-D reciprocal rank fusion of BM25 + semantic
"""
from __future__ import annotations

from typing import Any, Optional

from neeshops.config.settings import load_strategy
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate, Retriever
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.candidate_merge import merge_rrf, merge_weighted, stamp_provenance
from neeshops.retrieval.semantic import SemanticRetriever
from neeshops.utils.logging import log_event

STRATEGIES = ("bm25_only", "semantic_only", "hybrid", "fused")


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
        # Sub-retrievers need the same strategy view (e.g. the per-token
        # pooling flag, the semantic feature flag) — inject it when the
        # caller supplied an experiment config so config changes flow
        # without reconstructing the index.
        if strategy is not None:
            if hasattr(self.bm25, "set_strategy"):
                self.bm25.set_strategy(strategy)
            if hasattr(self.semantic, "set_strategy"):
                self.semantic.set_strategy(strategy)

    def weights_for_route(self, route: Optional[str]) -> dict[str, float]:
        route_key = route if route in ("buying", "browsing") else "browsing"
        route_cfg = self._strategy["retrieval"][route_key]
        return {"bm25": route_cfg["bm25_weight"], "semantic": route_cfg["semantic_weight"]}

    def _retrieval_cfg(self) -> dict[str, Any]:
        return self._strategy.get("retrieval", {})

    def _strategy_mode(self) -> str:
        mode = self._retrieval_cfg().get("strategy", "hybrid")
        if mode not in STRATEGIES:
            log_event("retrieval.strategy_unknown", requested=mode, fallback="hybrid")
            return "hybrid"
        return mode

    def _single_source(
        self, source: str, query: str, state: ConversationState, top_k: int
    ) -> list[Candidate]:
        retriever = self.bm25 if source == "bm25" else self.semantic
        if not retriever.is_available():
            return []
        return stamp_provenance(retriever.search(query, state, top_k), source)

    def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
        cfg = self._retrieval_cfg()
        mode = self._strategy_mode()
        candidate_limit = cfg.get("candidate_limit", 200)

        if mode == "bm25_only":
            if self.bm25.is_available():
                merged = self._single_source("bm25", query, state, candidate_limit)
            else:
                # Never hand back an empty pool while another retriever works.
                log_event(
                    "retrieval.fallback", requested=mode, to="semantic",
                    reason="bm25 unavailable",
                )
                merged = self._single_source("semantic", query, state, candidate_limit)
        elif mode == "semantic_only":
            if self.semantic.is_available():
                merged = self._single_source("semantic", query, state, candidate_limit)
            else:
                log_event(
                    "retrieval.fallback", requested=mode, to="bm25",
                    reason="semantic unavailable",
                )
                merged = self._single_source("bm25", query, state, candidate_limit)
        else:
            results: dict[str, list[Candidate]] = {}
            results["bm25"] = (
                self.bm25.search(query, state, candidate_limit)
                if self.bm25.is_available()
                else []
            )
            results["semantic"] = (
                self.semantic.search(query, state, candidate_limit)
                if self.semantic.is_available()
                else []
            )
            weights = self.weights_for_route(state.route)
            if mode == "fused":
                merged = merge_rrf(results, weights, k=int(cfg.get("rrf_k", 60)))
            else:
                merged = merge_weighted(results, weights)

        log_event(
            "retrieval.hybrid",
            session_id=state.session_id,
            route=state.route,
            strategy=mode,
            weights=self.weights_for_route(state.route) if mode in ("hybrid", "fused") else None,
            bm25_count=sum(1 for c in merged if "bm25" in c.source.split("+")),
            semantic_count=sum(1 for c in merged if "semantic" in c.source.split("+")),
            merged_count=len(merged),
        )
        return merged[:top_k] if top_k else merged

    def search_multi(
        self,
        queries: dict[str, str],
        state: ConversationState,
        top_k: int,
    ) -> list[Candidate]:
        """Run several per-angle queries ({"accumulated", "latest",
        "constraints"} from NeeShopsAgent.build_retrieval_queries) and fuse
        them with reciprocal rank fusion: a product surfacing under multiple
        angles outranks one found by a single angle, which lifts pool recall
        for hard cases where the long accumulated OR-query alone dilutes
        BM25 ordering.

        Falls back to plain single-query `search()` when multi_query is
        disabled or fewer than two non-empty queries remain.
        """
        cfg = self._retrieval_cfg()
        mq_cfg = cfg.get("multi_query") or {}
        non_empty = {role: q for role, q in queries.items() if q and q.strip()}
        if not mq_cfg.get("enabled", True) or len(non_empty) <= 1:
            joined = " ".join(q for q in queries.values() if q)
            return self.search(joined, state, top_k)

        candidate_limit = cfg.get("candidate_limit", 200)
        role_weights = mq_cfg.get("weights") or {}
        lists: dict[str, list[Candidate]] = {}
        weights: dict[str, float] = {}
        for role, query in non_empty.items():
            weight = float(role_weights.get(role, 1.0))
            if self.bm25.is_available():
                lists[f"bm25:{role}"] = stamp_provenance(
                    self.bm25.search(query, state, candidate_limit), f"bm25:{role}"
                )
                weights[f"bm25:{role}"] = weight
            if self.semantic.is_available():
                lists[f"semantic:{role}"] = stamp_provenance(
                    self.semantic.search(query, state, candidate_limit), f"semantic:{role}"
                )
                weights[f"semantic:{role}"] = weight

        merged = merge_rrf(lists, weights, k=int(cfg.get("rrf_k", 60)))
        log_event(
            "retrieval.multi_query",
            session_id=state.session_id,
            route=state.route,
            query_roles={role: len(q.split()) for role, q in non_empty.items()},
            merged_count=len(merged),
        )
        return merged[:top_k] if top_k else merged
