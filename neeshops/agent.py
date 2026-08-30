"""NeeShopsAgent — orchestration only.

Wires together conversation state, intent/clarification, retrieval and
ranking into one turn. It deliberately contains no search/ranking
implementation itself — see docs/neeshops/ARCHITECTURE.md for the pipeline diagram
and neeshops/{conversation,retrieval,ranking}/ for the actual logic.

This is what starter/agent.py adapts to the organiser's required
`starter.agent.Agent` contract.

Turn pipeline (v2):

    extract → route → multi-query retrieval → GUARANTEE POOL (exact Boolean
    AND over the token index, front-loaded) → filters (fast path) → rank
    (ALWAYS — every turn carries recommendations) → clarification gates →
    apply state → respond.

Key invariants:
- Recommendations are emitted on EVERY turn (a question turn still carries
  the top-10 — the contract allows and scores both, so a question never
  forfeits the turn's hit chance).
- The guarantee pool is front-loaded so exact AND matches survive the
  ranker's rerank window truncation.
- This turn's extracted constraints apply to filtering/ranking/decisions
  immediately (preview state), not one turn late.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from neeshops.config.settings import get_settings, load_strategy
from neeshops.conversation.clarification import ClarificationEngine
from neeshops.conversation.constraints import extract_constraints, is_intent_override
from neeshops.conversation.intent import detect_route
from neeshops.conversation.state import StateManager, _is_real_value
from neeshops.models.session import NO_PREFERENCE
from neeshops.ranking.base import Ranker
from neeshops.ranking.deterministic import ConstraintAwareRanker
from neeshops.ranking.llm_reranker import LLMReranker
from neeshops.retrieval.base import Candidate, Retriever
from neeshops.retrieval.filters import apply_filters
from neeshops.retrieval.hybrid import HybridRetriever
from neeshops.retrieval.token_index import (
    TokenIndex,
    constraint_token_groups,
    get_or_build_index,
)
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
        catalog_path: Optional[Path] = None,
    ) -> None:
        self.strategy = strategy or load_strategy()
        self.state_manager = state_manager or StateManager(
            inferred_decay=float(self.strategy.get("intent", {}).get("inferred_decay", 0.9))
        )
        self.retriever = retriever or HybridRetriever(strategy=self.strategy)
        # ConstraintAwareRanker orders by explicit-constraint violations
        # first, then weighted local features (config: ranking.deterministic)
        # — every answered constraint actively moves matching products up.
        self.catalog_lookup = catalog_lookup or {}
        self.catalog_path = Path(catalog_path) if catalog_path else None
        # Shared read-only Boolean token index (guarantee pool, fast
        # filters, coverage×IDF features). Built once per catalog file.
        self.token_index = get_or_build_index(self.catalog_lookup, self.catalog_path)
        # ConstraintAwareRanker orders by explicit-constraint violations
        # first, then constraint coverage (IDF-weighted), then weighted
        # local features (config: ranking.deterministic) — every answered
        # constraint actively moves matching products up.
        base_ranker = ranker or ConstraintAwareRanker(
            strategy=self.strategy, token_index=self.token_index
        )
        # Tier-2 of the ranking stage (gated LLM rerank) wraps the
        # deterministic ranker; it is OFF by default (feature flag / env)
        # and every path fails soft to the deterministic baseline.
        if isinstance(base_ranker, ConstraintAwareRanker) and (
            self.strategy.get("feature_flags", {}).get("enable_llm_reranker")
            or get_settings().enable_llm_reranker
        ):
            from neeshops.ranking.llm_reranker import LLMReranker

            self.ranker: Ranker = LLMReranker(
                strategy=self.strategy,
                fallback=base_ranker,
                token_index=self.token_index,
            )
        else:
            self.ranker = base_ranker
        # Crash-containment tier (Ranker protocol): respond() routes here
        # when the configured ranker reports unavailable or raises — the
        # agent must never fail a turn because an optional tier did.
        self._fallback_ranker: Ranker = ConstraintAwareRanker(
            strategy=self.strategy, token_index=self.token_index
        )
        self.clarification_engine = clarification_engine or ClarificationEngine(
            strategy=self.strategy, catalog_lookup=self.catalog_lookup
        )
        # Transient per-turn pools (instrumentation only — not session state).
        self.last_candidates: list[Candidate] = []
        self.last_hybrid_pool: list[Candidate] = []

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
        # by the requirement extractor). Stale-slot erasure is handled by
        # apply_turn: the previous intent's slots move to the stale bucket
        # (weak 0.3 ranking weight, recoverable on re-affirmation) so the
        # new intent rewrites the picture instead of fighting the old one.
        override = is_intent_override(user_message)
        if override:
            slot = None
        else:
            # If we asked a question last turn, this message is primarily
            # the answer to it — let the extractor slot-fill that attribute.
            slot = state.history[-1].asked_attribute if state.history else None

        extracted = extract_constraints(user_message, slot=slot)
        route = detect_route(user_message, state.route, len(state.constraints))

        # Provisional view: this turn's extraction applies to the whole
        # pipeline immediately (contradictions stale old values in preview,
        # the freshly detected route replaces the previous one).
        preview_state = self._preview_state(
            state, extracted, route=route, turn=turn
        )

        # Retrieval is fault-contained: a crashed/disconnected retriever
        # degrades to an empty pool (never an exception out of respond).
        try:
            candidates, guarantee_info = self.build_candidates(
                state, user_message, extracted, preview_state=preview_state
            )
        except Exception as exc:  # noqa: BLE001 - reliability contract
            log_event("agent.retrieval_failed", session_id=session_id, error=str(exc))
            candidates, guarantee_info = [], self._empty_guarantee_info()
        # Transient last-turn pool (for instrumentation panels — the exact
        # production pool this turn ranked, no recomputation needed).
        self.last_candidates = candidates

        # ALWAYS rank — a question turn still carries recommendations (the
        # contract allows both, the evaluator scores both).
        recommendations: list[Any] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        llm_latency_ms: float | None = None
        llm_fallback: str | None = None
        llm_used = False
        if candidates:
            ranker = self.ranker if self.ranker.is_available() else self._fallback_ranker
            try:
                result = ranker.rank(
                    candidates, self.catalog_lookup, preview_state, top_k
                )
            except Exception as exc:  # noqa: BLE001 - reliability contract
                log_event(
                    "agent.ranker_failed",
                    session_id=session_id,
                    ranker=getattr(ranker, "name", type(ranker).__name__),
                    error=str(exc),
                )
                result = self._fallback_ranker.rank(
                    candidates, self.catalog_lookup, preview_state, top_k
                )
            if isinstance(result, tuple) and len(result) == 2:
                recommendations, rank_usage = result
                if isinstance(rank_usage, dict):
                    for key in ("prompt_tokens", "completion_tokens"):
                        value = rank_usage.get(key)
                        if isinstance(value, int) and value >= 0:
                            usage[key] = value
            else:
                recommendations = result
            if isinstance(self.ranker, LLMReranker):
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
            else:
                # Ranker protocol usage (Ranker.get_usage). The base default
                # is all-zero, so only real counts overwrite the response.
                proto_usage = ranker.get_usage()
                if isinstance(proto_usage, dict):
                    pt = proto_usage.get("prompt_tokens")
                    ct = proto_usage.get("completion_tokens")
                    if isinstance(pt, int) and pt >= 0 and (pt or ct):
                        usage["prompt_tokens"] = pt
                        if isinstance(ct, int) and ct >= 0:
                            usage["completion_tokens"] = ct

        # The PREVIEW state drives the decision, not the pre-turn state:
        # a no-preference answer given THIS turn must be visible now, or
        # the clarification engine re-asks the same attribute (the wildcard
        # "other" was asked again immediately after a no-preference reply).
        decision = self.clarification_engine.decide(
            preview_state,
            candidates,
            turn,
            context=self._clarification_context(
                preview_state, candidates, guarantee_info, recommendations
            ),
        )

        state = self.state_manager.apply_turn(
            session_id=session_id,
            turn=turn,
            user_message=user_message,
            extracted_constraints=extracted,
            route=route,
            asked_attribute=decision["ask_attribute"],
            inferred=decision.get("inferred"),
        )
        if recommendations:
            self.state_manager.record_recommendations(
                session_id, [r.parent_asin for r in recommendations]
            )

        message = decision["question"] or self._default_message(recommendations)

        latency_ms = (time.perf_counter() - start) * 1000
        diagnostics = {
            "turn": turn,
            "route": route,
            "pool_size": len(candidates),
            "and_set_size": guarantee_info.get("and_set_size"),
            "guarantee_ids": guarantee_info.get("guarantee_ids", 0),
            "padded_ids": guarantee_info.get("padded_ids", 0),
            "dropped_groups": [
                sorted(g) for g in guarantee_info.get("dropped_groups", [])
            ],
            "over_generality": guarantee_info.get("over_generality", False),
            "asked_attribute": decision["ask_attribute"],
            "decision_gate": decision.get("gate"),
            "llm_fallback": llm_fallback,
            "llm_used": llm_used,
        }
        log_event(
            "agent.respond",
            session_id=session_id,
            turn=turn,
            route=route,
            candidate_count=len(candidates),
            recommendation_count=len(recommendations),
            asked_attribute=decision["ask_attribute"],
            and_set_size=guarantee_info.get("and_set_size"),
            over_generality=guarantee_info.get("over_generality", False),
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
            "diagnostics": diagnostics,
            # Extra internal-only field (route) is stripped by
            # starter/agent.py before returning to the official evaluator,
            # whose docs/agent_api_contract.json forbids additional
            # properties on the turn response — keep it here only for our
            # own logging/frontend/instrumentation use.
            "route": route,
        }

    # -- candidate pipeline (public: diagnostics scripts replicate it) ------

    def build_candidates(
        self,
        state: Any,
        user_message: str,
        extracted: Optional[dict[str, Any]] = None,
        preview_state: Optional[Any] = None,
    ) -> tuple[list[Candidate], dict[str, Any]]:
        """Retrieval → guarantee pool → filters → top-up. Returns the
        bounded candidate pool plus guarantee diagnostics. Public so
        scripts/run_oracle_eval.py replicates the exact production pool."""
        view = preview_state if preview_state is not None else self._preview_state(
            state, extracted
        )
        queries = self.build_retrieval_queries(state, user_message, extracted)
        limit = int(self.strategy["retrieval"].get("candidate_limit", 200))

        # Retrieval runs against the PREVIEW state: this turn's route must
        # drive the route weights, and retrievers observe the constraints
        # stated this turn (search() receives state for exactly this).
        search_multi = getattr(self.retriever, "search_multi", None)
        if search_multi is not None:
            hybrid_pool = search_multi(queries, view, top_k=limit)
        else:
            # Plain Retriever implementations only expose search() — run
            # the angle queries as one joined query.
            joined = " ".join(q for q in queries.values() if q)
            hybrid_pool = self.retriever.search(joined, view, top_k=limit)
        self.last_hybrid_pool = hybrid_pool
        info = self._guarantee_info(view)
        candidates = self._priority_union(hybrid_pool, info, limit)

        if self.catalog_lookup:
            candidates = apply_filters(
                candidates, self.catalog_lookup, view, token_index=self.token_index
            )
            candidates = self._topup_pool(candidates, view, info, limit)
        return candidates, info

    @staticmethod
    def _empty_guarantee_info() -> dict[str, Any]:
        """Zeroed guarantee diagnostics — the retrieval-failed shape."""
        return {
            "groups": [],
            "ids": [],
            "plausible_ids": [],
            "dropped_groups": [],
            "and_set_size": None,
            "guarantee_ids": 0,
            "padded_ids": 0,
            "over_generality": False,
        }

    def _guarantee_info(self, view_state: Any) -> dict[str, Any]:
        """Compute the exact Boolean AND set (the guarantee tier)."""
        info: dict[str, Any] = self._empty_guarantee_info()
        if self.token_index is None:
            return info
        guarantee_cfg = self.strategy["retrieval"].get("guarantee", {})
        if not guarantee_cfg.get("enabled", True):
            return info
        groups = constraint_token_groups(view_state.constraints)
        info["groups"] = groups
        if not groups:
            return info
        price_cap = self._budget_cap(view_state)
        plausible_limit = int(guarantee_cfg.get("plausible_set_limit", 200))
        and_ids = self.token_index.and_search_groups(groups, price_cap)
        info["and_set_size"] = len(and_ids)
        if len(and_ids) > plausible_limit:
            # Over-generality: the AND set is too broad to be a guarantee
            # tier — no guarantee (the pool cannot hold them all), but the
            # AND members are still every product that satisfies ALL
            # constraints: the pool prioritizes hybrid-corroborated AND
            # members, then popular AND members (see _priority_union), and
            # the clarification engine's over-generality gate asks the
            # set-splitting question (each answer shrinks the AND set,
            # after which the guarantee is exact).
            info["over_generality"] = True
            entropy_limit = int(
                self.strategy.get("clarification", {}).get("entropy_plausible_limit", 20000)
            )
            if len(and_ids) <= entropy_limit:
                info["plausible_ids"] = list(and_ids)
            info["and_ids_full"] = list(and_ids)
            return info
        if not and_ids:
            and_ids, dropped = self.token_index.and_search_backoff(
                groups, price_cap, min_ids=1
            )
            info["dropped_groups"] = dropped
            if dropped:
                log_event(
                    "guarantee.backoff",
                    dropped=[sorted(g) for g in dropped],
                    recovered=len(and_ids),
                )
        if not and_ids:
            return info
        entropy_limit = int(
            self.strategy.get("clarification", {}).get("entropy_plausible_limit", 5000)
        )
        if len(and_ids) <= entropy_limit:
            info["plausible_ids"] = list(and_ids)
        pre_pad = len(and_ids)
        # The guarantee floor is route-dependent: buying pads the pool wider
        # (ranking.rerank_floor_buying) because buying targets are crowded
        # out of the top-10 among full-coverage AND members; other routes
        # keep the default floor.
        floor = int(guarantee_cfg.get("rerank_floor", 40))
        if view_state.route == "buying":
            floor = int(
                self.strategy.get("ranking", {}).get("rerank_floor_buying", floor)
            )
        if len(and_ids) < floor:
            pad = self.token_index.coverage_rank(
                groups, price_cap, limit=floor * 4
            )
            existing = set(and_ids)
            for asin in pad:
                if len(and_ids) >= floor:
                    break
                if asin not in existing:
                    and_ids.append(asin)
                    existing.add(asin)
        info["ids"] = and_ids
        info["guarantee_ids"] = len(and_ids)
        info["padded_ids"] = max(len(and_ids) - pre_pad, 0)
        return info

    def _priority_union(
        self, hybrid_pool: list[Candidate], info: dict[str, Any], limit: int
    ) -> list[Candidate]:
        """Guarantee tier first, then the hybrid pool, dedup by asin.

        In the over-generality regime (AND set too broad for a guarantee
        tier) the pool still prioritizes the AND set: hybrid-corroborated
        members first, then popular AND members, then the hybrid remainder
        — every AND member satisfies ALL stated constraints, so they
        dominate any non-member regardless of retrieval score."""
        if info.get("over_generality") and info.get("and_ids_full"):
            and_set = set(info["and_ids_full"])
            corroborated: list[Candidate] = []
            rest: list[Candidate] = []
            seen: set[str] = set()
            for candidate in hybrid_pool:
                if candidate.parent_asin in seen:
                    continue
                seen.add(candidate.parent_asin)
                if candidate.parent_asin in and_set:
                    corroborated.append(candidate)
                else:
                    rest.append(candidate)
            popular_and = sorted(
                (asin for asin in info["and_ids_full"] if asin not in seen),
                key=lambda a: (-self.token_index.popularity(a), a),
            )
            out = corroborated
            for asin in popular_and:
                if len(out) >= limit:
                    return out
                out.append(
                    Candidate(
                        parent_asin=asin,
                        score=0.0,
                        source="and_popular",
                        metadata=None,
                    )
                )
            out.extend(rest)
            return out[:limit] if limit else out

        ids = info.get("ids") or []
        if not ids:
            return hybrid_pool[:limit] if limit else hybrid_pool
        max_score = max((c.score for c in hybrid_pool), default=1.0) or 1.0
        merged: list[Candidate] = []
        seen: set[str] = set()
        for i, asin in enumerate(ids):
            if asin in seen:
                continue
            seen.add(asin)
            merged.append(
                Candidate(
                    parent_asin=asin,
                    score=max_score * (1.0 - i / (len(ids) + 1.0)),
                    source="guarantee",
                    metadata={"rank": i + 1},
                )
            )
        for candidate in hybrid_pool:
            if candidate.parent_asin not in seen:
                seen.add(candidate.parent_asin)
                merged.append(candidate)
        return merged[:limit] if limit else merged

    def _topup_pool(
        self,
        candidates: list[Candidate],
        view_state: Any,
        info: dict[str, Any],
        limit: int,
    ) -> list[Candidate]:
        """Affordable token-match top-up: if filtering shrank the pool below
        the rerank floor, add partial (coverage-ranked) matches — the budget
        hard-drop already removed over-budget items, so this restores pool
        breadth without violating the budget. Slot allocation only; never
        relaxes ranking demotion."""
        if self.token_index is None or len(candidates) >= limit:
            return candidates
        min_topup = int(
            self.strategy["retrieval"].get("min_pool_topup", 40)
        )
        if not min_topup or len(candidates) >= min_topup:
            return candidates
        groups = info.get("groups") or constraint_token_groups(view_state.constraints)
        if not groups:
            return candidates
        present = {c.parent_asin for c in candidates}
        target_size = min(min_topup, limit)
        pad = self.token_index.coverage_rank(
            groups, self._budget_cap(view_state), limit=limit
        )
        out = list(candidates)
        for asin in pad:
            if len(out) >= target_size:
                break
            if asin not in present:
                present.add(asin)
                out.append(
                    Candidate(parent_asin=asin, score=0.0, source="coverage_pad")
                )
        return out

    def _budget_cap(self, view_state: Any) -> Optional[float]:
        budget = view_state.constraints.get("budget")
        if budget is None or budget == NO_PREFERENCE:
            return None
        try:
            value = float(budget)
        except (TypeError, ValueError):
            return None
        tolerance = float(
            self.strategy.get("filters", {}).get("budget_tolerance", 1.10)
        )
        return value * tolerance if value > 0 else None

    def _preview_state(
        self,
        state: Any,
        extracted: Optional[dict[str, Any]] = None,
        route: Optional[str] = None,
        turn: Optional[int] = None,
    ) -> Any:
        """State as it will look after apply_turn records this exchange —
        used for filtering/ranking/retrieval/decisions so a constraint
        extracted NOW applies NOW (filters used to lag one turn behind).
        Mirrors the slot lifecycle in StateManager.apply_turn (contradiction
        staling, re-affirmation recovery) without appending history, and
        carries this turn's route and turn number."""
        constraints = dict(state.constraints)
        stale = dict(getattr(state, "stale", None) or {})
        for field, value in (extracted or {}).items():
            old = constraints.get(field)
            if field in stale and stale[field] == value:
                stale.pop(field)  # re-affirmed — recover the slot
            elif _is_real_value(old) and old != value:
                stale[field] = old
            constraints[field] = value
        updates: dict[str, Any] = {
            "constraints": constraints,
            "stale": stale,
            "inferred": dict(getattr(state, "inferred", None) or {}),
        }
        if route:
            updates["route"] = route
        if turn is not None:
            updates["turn"] = turn
        return state.model_copy(update=updates)

    def _clarification_context(
        self,
        preview_state: Any,
        candidates: list[Candidate],
        guarantee_info: dict[str, Any],
        recommendations: list[Any],
    ) -> dict[str, Any]:
        return {
            "and_set_size": guarantee_info.get("and_set_size"),
            "over_generality": guarantee_info.get("over_generality", False),
            "dropped_groups": guarantee_info.get("dropped_groups", []),
            "groups": guarantee_info.get("groups", []),
            "plausible_ids": guarantee_info.get("plausible_ids", []),
            "token_index": self.token_index,
            "candidate_limit": int(
                self.strategy["retrieval"].get("candidate_limit", 200)
            ),
            "ranked": [r.parent_asin for r in recommendations],
            "ranked_scores": [r.score for r in recommendations],
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
          the pool entirely on non-informative turns. This includes
          pre-override text: measured on the 200-session panel, cutting
          the accumulation at the override turn dropped the target out of
          the hybrid pool after the override (the opener's category words
          are the strongest target-matching tokens), so the disclaimed
          intent is deactivated at the CONSTRAINT level only.
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
        accumulation too — measured on the 200-session panel, cutting it
        at the override turn dropped the target out of the hybrid pool;
        the disclaimed intent is instead deactivated at the constraint
        level, which does not remove its text from the target's own
        retrieval signal.)"""
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
