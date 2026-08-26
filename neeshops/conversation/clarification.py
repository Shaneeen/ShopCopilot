"""Clarification engine: should we ask a question, recommend now, or both?

The organiser's Agent contract allows a message + recommendations in the
same turn, so "should_recommend" and "ask_attribute" are independent
decisions, not a branch.

Stage-1 implementation is rule-based (candidate-pool size + missing
constraints + a question budget). The interface is stable so it can be
swapped for something smarter without touching neeshops/agent.py.
"""
from __future__ import annotations

from typing import Any, Optional

from neeshops.models.session import CONSTRAINT_FIELDS, ConversationState
from neeshops.config.settings import load_strategy

_QUESTIONS = {
    "use_case": "What will you mainly use it for?",
    "style": "What style are you going for — casual, or something dressier?",
    "budget": "Do you have a budget in mind?",
    "color": "Any colour preference?",
    "size": "What size should I look for?",
    "material": "Any material you prefer, or want to avoid?",
    "brand": "Any brand you like, or want to avoid?",
}


class ClarificationEngine:
    def __init__(self, strategy: Optional[dict[str, Any]] = None) -> None:
        self._cfg = (strategy or load_strategy())["clarification"]

    def decide(
        self,
        state: ConversationState,
        candidates: list[Any],
        turn: int,
    ) -> dict[str, Any]:
        """Return {"ask_attribute", "question", "should_recommend"}.

        `ask_attribute`/`question` are None when there's nothing useful left
        to ask (question budget spent, or every field is known/no-preference).
        """
        candidate_count = len(candidates)
        questions_asked = len(state.asked_attributes)
        budget_left = questions_asked < self._cfg["max_questions_per_session"]

        # Recommend once the pool meets the threshold, or — once there's
        # nothing left worth asking — recommend from whatever we have
        # rather than leave the user with neither a question nor a result.
        should_recommend = candidate_count > 0 and (
            candidate_count >= self._cfg["min_candidates_before_recommend"]
            or not budget_left
        )

        ask_attribute = None
        question = None
        # Ask when the pool is too broad to rank confidently, OR too narrow
        # to satisfy min_candidates_before_recommend — either way a missing
        # constraint is worth asking about. Without the "too narrow" arm, a
        # small-but-nonzero candidate pool would fall through with neither a
        # question nor a recommendation.
        pool_needs_narrowing = candidate_count > self._cfg["ask_if_candidates_above"]
        pool_too_thin = candidate_count < self._cfg["min_candidates_before_recommend"]

        if budget_left and (pool_needs_narrowing or pool_too_thin):
            missing = self._next_missing_field(state)
            if missing:
                ask_attribute = missing
                question = _QUESTIONS.get(missing, f"Do you have a preference for {missing}?")

        return {
            "ask_attribute": ask_attribute,
            "question": question,
            "should_recommend": should_recommend,
        }

    @staticmethod
    def _next_missing_field(state: ConversationState) -> Optional[str]:
        for field in CONSTRAINT_FIELDS:
            if state.is_unset(field) and field not in state.asked_attributes:
                return field
        return None
