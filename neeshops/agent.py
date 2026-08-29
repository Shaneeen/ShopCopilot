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
from neeshops.conversation.constraints import extract_constraints, is_intent_override
from neeshops.conversation.intent import detect_route
from neeshops.conversation.state import StateManager
from neeshops.models.session import NO_PREFERENCE
from neeshops.ranking.base import Ranker
from neeshops.ranking.deterministic import ConstraintAwareRanker
from neeshops.retrieval.base import Retriever
from neeshops.retrieval.hybrid import HybridRetriever
from neeshops.utils.logging import log_event
from neeshops.utils.tokens import keywords


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
        # ConstraintAwareRanker orders by explicit-constraint violations
        # first, then weighted local features (config: ranking.deterministic)
        # — every answered constraint actively moves matching products up.
        self.ranker = ranker or ConstraintAwareRanker(strategy=self.strategy)
        # parent_asin -> raw catalog row, for filtering/ranking/personalization.
        # Populate via load_catalog_lookup() (scripts/setup_catalog.py) —
        # an empty lookup degrades gracefully (filters/personalization no-op).
        self.catalog_lookup = catalog_lookup or {}
        self.clarification_engine = clarification_engine or ClarificationEngine(
            strategy=self.strategy, catalog_lookup=self.catalog_lookup
        )

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

        # An intent-override turn is an instruction, not a slot answer —
        # parse it fresh (its "What I need is: X" requirement is picked up
        # by the requirement extractor) but keep everything learned so far:
        # the user's actual target never changes, so earlier answers stay
        # true and the new requirement just adds signal.
        if is_intent_override(user_message):
            slot = None
        else:
            # If we asked a question last turn, this message is primarily
            # the answer to it — let the extractor slot-fill that attribute.
            slot = state.history[-1].asked_attribute if state.history else None

        extracted = extract_constraints(user_message, slot=slot)
        route = detect_route(user_message, state.route, len(state.constraints))

        queries = self.build_retrieval_queries(state, user_message, extracted)

        # Retrieve first (pre-clarification) so the clarification engine can
        # see how broad/narrow the candidate pool already is.
        candidates = self.retriever.search_multi(
            queries, state, top_k=self.strategy["retrieval"]["candidate_limit"]
        )

        if self.catalog_lookup:
            from neeshops.retrieval.filters import apply_filters

            candidates = apply_filters(candidates, self.catalog_lookup, state)

        decision = self.clarification_engine.decide(state, candidates, turn)

        state = self.state_manager.apply_turn(
            session_id=session_id,
            turn=turn,
            user_message=user_message,
            extracted_constraints=extracted,
            route=route,
            asked_attribute=decision["ask_attribute"],
        )

        recommendations = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        llm_latency_ms: float | None = None
        llm_fallback: str | None = None
        llm_used = False
        if decision["should_recommend"] and candidates:
            recommendations = self.ranker.rank(
                candidates, self.catalog_lookup, state, top_k=top_k
            )
            self.state_manager.record_recommendations(
                session_id, [r.parent_asin for r in recommendations]
            )
            llm_latency_ms = getattr(self.ranker, "last_latency_ms", None)
            llm_fallback = getattr(self.ranker, "last_fallback_reason", None)
            raw_usage = getattr(self.ranker, "last_usage", None)
            if isinstance(raw_usage, dict):
                pt = raw_usage.get("prompt_tokens")
                ct = raw_usage.get("completion_tokens")
                if isinstance(pt, int):
                    usage["prompt_tokens"] = pt
                if isinstance(ct, int):
                    usage["completion_tokens"] = ct
                llm_used = pt is not None or ct is not None
            if llm_latency_ms and llm_latency_ms > 0:
                llm_used = True

        message = decision["question"] or self._default_message(recommendations)

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
            llm_latency_ms=round(llm_latency_ms, 2)
            if isinstance(llm_latency_ms, (int, float))
            else None,
            llm_fallback=llm_fallback,
            llm_used=llm_used,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
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

    def build_retrieval_queries(
        self,
        state: Any,
        user_message: str,
        extracted: Optional[dict[str, Any]] = None,
    ) -> dict[str, str]:
        """The per-turn retrieval queries, fused by search_multi():

        - **accumulated** — keywords of everything the user has said so
          far. Clarification replies are short and often boilerplate ("I
          don't have an additional preference for budget") — rebuilding the
          query from the latest message alone let the target drop out of
          the pool entirely on non-informative turns.
        - **latest** — keywords of just this message. A long accumulated
          OR-query dilutes BM25 ordering; this angle rescues products that
          match only the newest, strongest signal.
        - **constraints** — known constraint values (category, colour,
          material, style, brand, feature, use_case), a third retrieval
          angle that surfaces products sharing the user's attribute words
          even when the intent phrasing doesn't.

        Public so diagnostics (scripts/run_oracle_eval.py) replicate the
        exact production retrieval for a message.
        """
        merged = {**state.constraints, **(extracted or {})}
        constraint_parts = [
            str(merged[field])
            for field in (
                "category", "color", "material", "style", "brand", "feature", "use_case",
            )
            if isinstance(merged.get(field), str)
            and merged.get(field) != NO_PREFERENCE
            and merged.get(field).strip()
        ]
        return {
            "accumulated": self._conversation_query(state, user_message),
            "latest": " ".join(keywords(user_message)),
            "constraints": " ".join(keywords(" ".join(constraint_parts))),
        }

    @staticmethod
    def _conversation_query(state: Any, user_message: str) -> str:
        """Retrieval query for this turn: the keywords of EVERYTHING the
        user has said so far, not just the latest message.

        Clarification replies are short and often boilerplate ("I don't
        have an additional preference for budget") — rebuilding the query
        from the latest message alone let the target drop out of the
        candidate pool entirely on every non-informative turn. Accumulating
        keeps the opening intent permanently in the query while new answers
        add discriminating tokens. (Intent-override messages keep the
        accumulation too — the user's actual target never changes, so
        earlier keywords stay true; only slot-filling is skipped.)
        """
        tokens: list[str] = []
        seen: set[str] = set()
        for msg in [t.user_message for t in state.history] + [user_message]:
            for token in keywords(msg):
                if token not in seen:
                    seen.add(token)
                    tokens.append(token)
        return " ".join(tokens)

    @staticmethod
    def _default_message(recommendations: list[Any]) -> str:
        if recommendations:
            return "Here's what I'd recommend based on what you've told me so far."
        return "Tell me a bit more about what you're looking for."
