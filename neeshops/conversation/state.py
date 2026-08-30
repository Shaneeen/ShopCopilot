"""Conversation state lifecycle: create, persist in-memory, and apply
updates extracted from a turn.

Owned by Workstream 1 (see docs/neeshops/TEAM_WORKSTREAMS.md). This module holds
*behaviour*; the data shape itself lives in neeshops.models.session so
other modules can import the schema without pulling in this logic.
"""
from __future__ import annotations

from typing import Optional

from neeshops.conversation.constraints import is_intent_override
from neeshops.models.session import (
    NO_PREFERENCE,
    ConversationState,
    InferredSlot,
    Turn,
    UserProfile,
)
from neeshops.utils.logging import log_event

# Weight of stale (erased) slots in ranking coverage — weak signal, never a
# demotion. Matches config intent.route_flip_erase_weight default.
STALE_SLOT_WEIGHT = 0.3

# Inferred slots decaying below this weight are pruned.
MIN_INFERRED_WEIGHT = 0.05


class StateManager:
    """In-memory session store.

    The organiser evaluator drives sessions sequentially and calls
    `reset()` before the first `respond()` of each session, so a plain dict
    keyed by session_id is sufficient — no external store needed for the
    competition harness. Nothing here ever touches disk: profiles and
    session state live and die with the process (isolated single-user
    sessions; no cross-session leakage).
    """

    def __init__(self, inferred_decay: float = 0.9) -> None:
        self._sessions: dict[str, ConversationState] = {}
        self._inferred_decay = float(inferred_decay)

    def reset(self, session_id: str, user_profile: Optional[dict] = None) -> ConversationState:
        profile = UserProfile(**(user_profile or {}))
        state = ConversationState(session_id=session_id, user_profile=profile)
        self._sessions[session_id] = state
        log_event("state.reset", session_id=session_id)
        return state

    def get(self, session_id: str) -> ConversationState:
        if session_id not in self._sessions:
            # Defensive: the contract requires reset() first, but don't crash
            # the evaluator over a missing reset — start a blank session.
            return self.reset(session_id)
        return self._sessions[session_id]

    def apply_turn(
        self,
        session_id: str,
        turn: int,
        user_message: str,
        extracted_constraints: dict[str, object],
        route: Optional[str],
        asked_attribute: Optional[str] = None,
        inferred: Optional[dict[str, object]] = None,
    ) -> ConversationState:
        """Merge newly-extracted constraints into state using **intent
        override** semantics: a new explicit value for a field replaces the
        old one outright — it never accumulates (e.g. color must become
        "black", not "blue, black").

        `extracted_constraints` values of NO_PREFERENCE are also stored, so
        the clarification engine never asks about that field again.

        Slot lifecycle (pillar II):
        - **Intent Override** — the harness's override message keeps the
          SAME target (old and new values both describe it), so wholesale
          erasure would destroy true constraints. Erasure happens at the
          value level instead: a new value differing from the old one
          stales the old value (excluded from filter demotion, weak 0.3
          ranking weight, recoverable on re-affirmation).
        - **Inferred slots** — agreement-inferred attributes decay with age
          (weight ×= inferred_decay per elapsed turn); explicit constraints
          never decay.
        """
        state = self.get(session_id)
        state.turn = turn
        if route:
            state.route = route

        # An intent-override turn is recorded (ConversationState.override_turn)
        # for diagnostics and future transition work, but constraints are
        # NOT cleared here: measured on the 200-session panel, deactivating
        # the disclaimed soft fields (and cutting the accumulated query at
        # the override turn) LOWERED override HitRate 0.80 → 0.67 — the
        # card's soft values describe the SAME target product, so they are
        # true ranking/retrieval signal, not stale preferences. Only the
        # normal per-field override semantics below apply (a new value
        # replaces the old one; the old value goes to the stale bucket).
        if is_intent_override(user_message):
            state.override_turn = turn

        for field, value in (extracted_constraints or {}).items():
            old = state.constraints.get(field)
            if field in state.stale and state.stale[field] == value:
                state.stale.pop(field)  # re-affirmed — recover the slot
            elif _is_real_value(old) and old != value:
                state.stale[field] = old
            state.constraints[field] = value  # override, not merge/append

        self._decay_inferred(state, turn)
        for field, value in (inferred or {}).items():
            if field in state.constraints:
                continue  # explicit constraints always win
            state.inferred[field] = InferredSlot(value=value, weight=1.0, updated_turn=turn)

        state.history.append(
            Turn(
                turn=turn,
                user_message=user_message,
                route=state.route,
                asked_attribute=asked_attribute,
                informative=_is_informative(extracted_constraints),
            )
        )
        if asked_attribute and asked_attribute not in state.asked_attributes:
            state.asked_attributes.append(asked_attribute)

        log_event(
            "state.apply_turn",
            session_id=session_id,
            turn=turn,
            route=state.route,
            constraints=state.constraints,
            stale=state.stale,
            inferred={k: v.value for k, v in state.inferred.items()},
        )
        return state

    def _decay_inferred(self, state: ConversationState, turn: int) -> None:
        """Age-based decay for inferred slots ONLY — explicit verbatim
        constraints never decay (age decay would weaken true constraints in
        the ~170 non-override sessions)."""
        factor = self._inferred_decay
        if not state.inferred or factor >= 1.0:
            return
        expired: list[str] = []
        for field, slot in state.inferred.items():
            elapsed = max(turn - slot.updated_turn, 0)
            slot.weight = slot.weight * (factor ** elapsed)
            slot.updated_turn = turn
            if slot.weight < MIN_INFERRED_WEIGHT:
                expired.append(field)
        for field in expired:
            state.inferred.pop(field)

    def record_recommendations(self, session_id: str, asins: list[str]) -> None:
        state = self.get(session_id)
        for asin in asins:
            if asin not in state.previous_recommendations:
                state.previous_recommendations.append(asin)

    def mark_no_preference(self, session_id: str, field: str) -> None:
        state = self.get(session_id)
        old = state.constraints.get(field)
        if _is_real_value(old):
            state.stale[field] = old
        state.constraints[field] = NO_PREFERENCE


def _is_real_value(value: object) -> bool:
    """A slot value that carries real signal (not unset, not a
    no-preference marker, not blank) — the only kind that goes stale."""
    if value is None or value == NO_PREFERENCE:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _is_informative(extracted_constraints: dict[str, object]) -> bool:
    """A message is informative when it yielded at least one usable value —
    NO_PREFERENCE markers and empty updates carry no product signal."""
    for value in (extracted_constraints or {}).values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if isinstance(value, str) and value.strip() and value != NO_PREFERENCE:
            return True
    return False
