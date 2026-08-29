"""Clarification engine: should we ask a question, recommend now, or both?

The organiser's Agent contract allows a message + recommendations in the
same turn, so "should_recommend" and "ask_attribute" are independent
decisions, not a branch.

Question selection (config: clarification.strategy):

- **wildcard-first (default gate)** — while the wildcard budget allows, ask
  the open question (`ask_attribute="other"`, contract-legal): its answer
  carries up to two constraints of ANY type (parsed compound in
  constraints.py), roughly double the information of a specific-attribute
  question, which often draws "I don't have an additional preference" and
  wastes the turn. The wildcard stops once its cap is reached, the user
  signals nothing-left-to-share, or their last two answers carried no new
  information.
- **adaptive (fallback)** — entropy over the candidate pool's value
  distributions picks the most informative specific attribute, skipping
  fields where one value covers >90% of the pool. Short-vocabulary fields
  (material, colour, budget, style, size) come before taxonomy-ish ones
  (category, brand). Question text is value-aware, e.g. "Any colour —
  black, brown, or tan?".
- **fixed** — first unset slot in CONSTRAINT_FIELDS order, no catalog data
  needed.

All modes degrade gracefully; the interface is stable: decide() takes only
(state, candidates, turn).
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Optional

from neeshops.conversation.constraints import value_from_row
from neeshops.config.settings import load_strategy
from neeshops.models.session import CONSTRAINT_FIELDS, NO_PREFERENCE, ConversationState

_QUESTIONS = {
    "use_case": "What will you mainly use it for?",
    "style": "What style are you going for — casual, or something dressier?",
    "budget": "Do you have a budget in mind?",
    "color": "Any colour preference?",
    "size": "What size should I look for?",
    "material": "Any material you prefer, or want to avoid?",
    "brand": "Any brand you like, or want to avoid?",
    "other": "To narrow this down — what else matters most: the material, the colour, or the price?",
}

# Attributes a shopper can typically answer with one short word the
# slot-filler parses reliably; taxonomy-ish fields come second.
_TIER1_FIELDS = ("material", "color", "budget", "style", "size")
_TIER2_FIELDS = ("category", "brand")


class ClarificationEngine:
    def __init__(
        self,
        strategy: Optional[dict[str, Any]] = None,
        catalog_lookup: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        self._cfg = (strategy or load_strategy())["clarification"]
        self._catalog_lookup = catalog_lookup or {}

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
        # Count real questions from history — asked_attributes is deduplicated
        # and would never exhaust the budget when one attribute repeats.
        questions_asked = sum(1 for t in state.history if t.asked_attribute)
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
        if budget_left and self._wildcard_available(state):
            # Wildcard-first: an open "what else matters?" question yields up
            # to two constraints of any type per answer, while a specific
            # attribute question often draws "I don't have an additional
            # preference" — a wasted turn. See extract_constraints for how
            # the compound reply is parsed.
            ask_attribute = "other"
            question = self._question_for("other", candidates)
        elif budget_left and candidate_count > self._cfg["ask_if_candidates_above"]:
            if (
                self._cfg.get("strategy") == "adaptive"
                and self._catalog_lookup
                and candidates
            ):
                ask_attribute = self._adaptive_attribute(state, candidates)
            if ask_attribute is None:
                ask_attribute = self._next_missing_field(state)
            if ask_attribute:
                question = self._question_for(ask_attribute, candidates)

        return {
            "ask_attribute": ask_attribute,
            "question": question,
            "should_recommend": should_recommend,
        }

    def _wildcard_available(self, state: ConversationState) -> bool:
        """Keep asking the wildcard while it still pays for itself: within
        the per-session cap, before the user says they've shared everything,
        and while their last two answers still carried new information."""
        other_asks = sum(1 for t in state.history if t.asked_attribute == "other")
        if other_asks >= int(self._cfg.get("other_max_asks", 3)):
            return False
        if state.constraints.get("other") == NO_PREFERENCE:
            return False
        asked_turns = [t for t in state.history if t.asked_attribute]
        if len(asked_turns) >= 2 and all(not t.informative for t in asked_turns[-2:]):
            return False
        return True

    # -- adaptive selection -------------------------------------------------

    def _adaptive_attribute(self, state: ConversationState, candidates: list[Any]) -> Optional[str]:
        """Most informative unset attribute, or None if none qualifies."""
        rows = [
            self._catalog_lookup[c.parent_asin]
            for c in candidates
            if c.parent_asin in self._catalog_lookup
        ]
        if len(rows) < 5:
            return None
        for tier in (_TIER1_FIELDS, _TIER2_FIELDS):
            best = self._best_in_tier(state, rows, tier)
            if best:
                return best
        return None

    @staticmethod
    def _best_in_tier(
        state: ConversationState, rows: list[dict[str, Any]], tier: tuple[str, ...]
    ) -> Optional[str]:
        scored: list[tuple[float, int, str]] = []
        for field in tier:
            if not state.is_unset(field) or field in state.asked_attributes:
                continue
            dist = Counter(
                v for v in (value_from_row(field, row) for row in rows) if v
            )
            if len(dist) < 2:
                continue
            total = sum(dist.values())
            top1_share = dist.most_common(1)[0][1] / total
            if top1_share > 0.9:
                continue  # pool already homogeneous on this field
            entropy = -sum(
                (count / total) * math.log(count / total) for count in dist.values()
            )
            # Tie-break deterministically by the canonical field order.
            scored.append((-entropy, CONSTRAINT_FIELDS.index(field), field))
        return min(scored)[2] if scored else None

    # -- question text ------------------------------------------------------

    def _question_for(self, field: str, candidates: list[Any]) -> str:
        values = self._top_values(field, candidates, n=3)
        if not values:
            return _QUESTIONS.get(field, f"Do you have a preference for {field}?")
        if field == "budget":
            return (
                f"What budget works — under ${values[0]}, under ${values[1]}, "
                "or flexible?"
            )
        quoted = ", ".join(values[:-1]) + f", or {values[-1]}"
        if field == "color":
            return f"Any colour — {quoted}?"
        if field == "material":
            return f"Any material preference — {quoted}?"
        if field == "category":
            return f"Which type are you after — {quoted}?"
        if field == "brand":
            return f"Any brand you like — {quoted}, or open to anything?"
        if field == "style":
            return f"What style are you going for — {quoted}?"
        return _QUESTIONS.get(field, f"Do you have a preference for {field}?")

    def _top_values(self, field: str, candidates: list[Any], n: int) -> list[str]:
        if not self._catalog_lookup or not candidates:
            return []
        dist = Counter(
            v
            for v in (
                value_from_row(field, self._catalog_lookup.get(c.parent_asin))
                for c in candidates
            )
            if v
        )
        if len(dist) < 2:
            return []
        if field == "budget":
            prices = sorted(float(v) for v in dist.elements())
            return [str(round(prices[len(prices) // 4])), str(round(prices[3 * len(prices) // 4]))]
        ordered = sorted(dist.items(), key=lambda kv: (-kv[1], kv[0]))
        return [str(v) for v, _ in ordered[:n]]

    # -- fixed fallback -----------------------------------------------------

    @staticmethod
    def _next_missing_field(state: ConversationState) -> Optional[str]:
        for field in CONSTRAINT_FIELDS:
            if state.is_unset(field) and field not in state.asked_attributes:
                return field
        return None
