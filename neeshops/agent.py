"""NeeShopsAgent — orchestration only.

Wires together conversation state, intent/clarification, retrieval and
ranking into one turn. It deliberately contains no search/ranking
implementation itself — see docs/neeshops/ARCHITECTURE.md for the pipeline diagram
and neeshops/{conversation,retrieval,ranking}/ for the actual logic.

This is what starter/agent.py adapts to the organiser's required
`starter.agent.Agent` contract.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from neeshops.config.settings import load_strategy
from neeshops.conversation.clarification import ClarificationEngine
from neeshops.conversation.constraints import extract_constraints
from neeshops.conversation.intent import detect_route
from neeshops.conversation.state import StateManager
from neeshops.ranking.base import Ranker
from neeshops.ranking.heuristic import HeuristicRanker
from neeshops.retrieval.base import Retriever
from neeshops.retrieval.hybrid import HybridRetriever
from neeshops.utils.logging import log_event
from neeshops.utils.tokenization import build_retrieval_query, keywords


def _build_ranker(strategy: dict[str, Any]) -> Ranker:
    """Config-driven ranker selection with fallback to HeuristicRanker."""
    flags = strategy.get("feature_flags", {})
    if flags.get("enable_llm_reranker", False):
        try:
            from neeshops.ranking.llm_reranker import LLMReranker

            rerank_limit = strategy.get("ranking", {}).get("rerank_limit", 40)
            llm_ranker = LLMReranker(top_n_to_rerank=rerank_limit)
            if llm_ranker.is_available():
                return llm_ranker
        except Exception:
            pass
    return HeuristicRanker(strategy=strategy)


class NeeShopsAgent:
    """Session-oriented orchestrator. One instance can serve many sessions —
    all session data lives in `self.state_manager`, not on `self`.
    """

    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        ranker: Optional[Ranker] = None,
        state_manager: Optional[StateManager] = None,
        clarification_engine: Optional[ClarificationEngine] = None,
        catalog_lookup: Optional[dict[str, dict[str, Any]]] = None,
        strategy: Optional[dict[str, Any]] = None,
    ) -> None:
        self.strategy = strategy or load_strategy()
        self.state_manager = state_manager or StateManager()
        self.retriever = retriever or HybridRetriever(strategy=self.strategy)
        self.ranker = ranker or _build_ranker(self.strategy)
        self.clarification_engine = clarification_engine or ClarificationEngine(
            strategy=self.strategy
        )
        # parent_asin -> raw catalog row, for filtering/ranking/personalization.
        # Populate via load_catalog_lookup() (scripts/setup_catalog.py) —
        # an empty lookup degrades gracefully (filters/personalization no-op).
        self.catalog_lookup = catalog_lookup or {}

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.state_manager.reset(session_id, user_profile)

    def respond(
        self,
        session_id: str,
        user_message: str,
        turn: int,
        top_k: int,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        state = self.state_manager.get(session_id)

        # 1. Extract constraints and detect route
        extracted = extract_constraints(user_message)
        route = detect_route(user_message, state.route, len(state.constraints))

        # 2. StateManager.apply_turn happens BEFORE retrieval & clarification
        # so state has up-to-date constraints, turn, and route on this turn
        state = self.state_manager.apply_turn(
            session_id=session_id,
            turn=turn,
            user_message=user_message,
            extracted_constraints=extracted,
            route=route,
        )

        # 3. Build enriched retrieval query from active constraints + history + newest message
        query = build_retrieval_query(user_message, state=state)

        # 4. Retrieve using updated state (route + candidate_limit)
        try:
            if hasattr(self.retriever, "is_available") and not self.retriever.is_available():
                candidates = []
            else:
                candidates = self.retriever.search(
                    query, state, top_k=self.strategy["retrieval"]["candidate_limit"]
                )
        except Exception:
            candidates = []

        # 4. Filter using updated state constraints
        if self.catalog_lookup and candidates:
            try:
                from neeshops.retrieval.filters import apply_filters

                candidates = apply_filters(candidates, self.catalog_lookup, state)
            except Exception:
                pass

        # 5. Clarification engine decides based on updated state and candidates
        try:
            decision = self.clarification_engine.decide(state, candidates, turn)
        except Exception:
            decision = {
                "ask_attribute": None,
                "question": None,
                "should_recommend": bool(candidates),
            }

        if decision.get("ask_attribute"):
            self.state_manager.record_asked_attribute(session_id, decision["ask_attribute"])

        # 6. Rank candidates (with fallback to HeuristicRanker if configured ranker is unavailable or fails)
        recommendations = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if decision.get("should_recommend") and candidates:
            try:
                if not self.ranker.is_available():
                    raise RuntimeError(f"Ranker '{self.ranker.name}' is unavailable")

                rank_result = self.ranker.rank(
                    candidates, self.catalog_lookup, state, top_k=top_k
                )
                if isinstance(rank_result, tuple) and len(rank_result) == 2:
                    recommendations, r_usage = rank_result
                    if isinstance(r_usage, dict):
                        usage = r_usage
                else:
                    recommendations = rank_result
                    if hasattr(self.ranker, "get_usage") and callable(self.ranker.get_usage):
                        usage = self.ranker.get_usage()
                    elif hasattr(self.ranker, "last_usage") and isinstance(self.ranker.last_usage, dict):
                        usage = self.ranker.last_usage
            except Exception:
                if not isinstance(self.ranker, HeuristicRanker):
                    try:
                        fallback = HeuristicRanker(strategy=self.strategy)
                        recommendations = fallback.rank(
                            candidates, self.catalog_lookup, state, top_k=top_k
                        )
                        usage = {"prompt_tokens": 0, "completion_tokens": 0}
                    except Exception:
                        recommendations = []
                else:
                    recommendations = []
            if recommendations:
                self.state_manager.record_recommendations(
                    session_id, [r.parent_asin for r in recommendations]
                )

        message = decision.get("question") or self._default_message(recommendations)

        latency_ms = (time.perf_counter() - start) * 1000
        log_event(
            "agent.respond",
            session_id=session_id,
            turn=turn,
            route=route,
            candidate_count=len(candidates),
            recommendation_count=len(recommendations),
            asked_attribute=decision["ask_attribute"],
            latency_ms=round(latency_ms, 2),
        )

        return {
            "message": message,
            "ask_attribute": decision["ask_attribute"],
            "recommendations": [
                {"parent_asin": r.parent_asin, "score": r.score, "reason": r.reason}
                for r in recommendations
            ],
            "usage": usage,
            # Extra internal-only field (route) is stripped by
            # starter/agent.py before returning to the official evaluator,
            # whose docs/agent_api_contract.json forbids additional
            # properties on the turn response — keep it here only for our
            # own logging/frontend use.
            "route": route,
        }

    @staticmethod
    def _default_message(recommendations: list[Any]) -> str:
        if recommendations:
            return "Here's what I'd recommend based on what you've told me so far."
        return "Tell me a bit more about what you're looking for."
