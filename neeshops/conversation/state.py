"""Conversation state lifecycle: create, persist in-memory, and apply
updates extracted from a turn.

Owned by Workstream 1 (see docs/neeshops/TEAM_WORKSTREAMS.md). This module holds
*behaviour*; the data shape itself lives in neeshops.models.session so
other modules can import the schema without pulling in this logic.
"""
from __future__ import annotations

from typing import Optional

from neeshops.models.session import (
    NO_PREFERENCE,
    ConversationState,
    Turn,
    UserProfile,
)
from neeshops.utils.logging import log_event


class StateManager:
    """In-memory session store.

    The organiser evaluator drives sessions sequentially and calls
    `reset()` before the first `respond()` of each session, so a plain dict
    keyed by session_id is sufficient — no external store needed for the
    competition harness.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationState] = {}

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
    ) -> ConversationState:
        """Merge newly-extracted constraints into state using **intent
        override** semantics: a new explicit value for a field replaces the
        old one outright — it never accumulates (e.g. color must become
        "black", not "blue, black").

        `extracted_constraints` values of NO_PREFERENCE are also stored, so
        the clarification engine never asks about that field again.
        """
        state = self.get(session_id)
        state.turn = turn
        if route:
            state.route = route

        for field, value in extracted_constraints.items():
            state.constraints[field] = value  # override, not merge/append

        state.history.append(
            Turn(
                turn=turn,
                user_message=user_message,
                route=state.route,
                asked_attribute=asked_attribute,
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
        )
        return state

    def record_asked_attribute(self, session_id: str, attribute: Optional[str]) -> None:
        if not attribute:
            return
        state = self.get(session_id)
        if attribute not in state.asked_attributes:
            state.asked_attributes.append(attribute)
        if state.history:
            state.history[-1].asked_attribute = attribute

    def record_recommendations(self, session_id: str, asins: list[str]) -> None:
        state = self.get(session_id)
        for asin in asins:
            if asin not in state.previous_recommendations:
                state.previous_recommendations.append(asin)

    def mark_no_preference(self, session_id: str, field: str) -> None:
        state = self.get(session_id)
        state.constraints[field] = NO_PREFERENCE
