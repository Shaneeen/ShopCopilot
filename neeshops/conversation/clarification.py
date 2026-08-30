"""Clarification engine: should we ask a question, recommend now, or both?

The organiser's Agent contract allows a message + recommendations in the
same turn, so "should_recommend" and "ask_attribute" are independent
decisions, not a branch — and the agent ALWAYS ranks, so a question never
forfeits the current turn's hit chance. Caps optimize the 0.2-weighted
efficiency term at the 0.5-weighted Hit term's expense; these GATES achieve
"as few questions as possible" per session instead (0 when the pool is
pinned, 3-4 when it genuinely isn't), with a hard turn-guard so the 10-turn
zero-score limit is structurally unreachable.

Gate order (first match wins; every return also recommends):

1. **exhausted**      — question budget spent (max_questions_per_session)
2. **turn_guard**     — turn > last_question_turn → never ask again (turns
                        9-10 are pure recommendations; a question on turn 9
                        still informs turn 10's scored recommendations)
3. **small_pool**     — pool < min_candidates_before_recommend → recommend
4. **confident**      — top-10 all satisfy every constraint (coverage 1.0)
                        AND the rank-1 margin ≥ margin_stop → recommend
5. **wildcard**       — open "what else matters?" question, phrased to
                        invite a compound reply ("black; cotton") which the
                        parser splits into TWO constraint slots per turn.
                        One turn, up to two constraints.
6. **over_generality** — the plausible-target set (Boolean AND set) exceeds
                        plausible_set_limit, or no constraints + a
                        maxed-out pool: pillar II Proactive Guidance —
                        retrieval breadth is cut and the max set-splitting
                        question is asked NOW. Each answer shrinks the AND
                        set, after which the guarantee tier is exact.
7. **agreement**      — the top-10 pool unanimously agrees on an un-asked
                        attribute's value: record it as an INFERRED slot
                        (bonus-only, decaying — never a filter) and skip.
8. **entropy**        — otherwise ask the un-asked tier-1 attribute with
                        maximum entropy. When the plausible AND set is
                        small enough, the value distribution runs over THAT
                        set — literally the question that best splits the
                        items that could still be the target — with the
                        expected AND-set reduction as tie-breaker; otherwise
                        rank-weighted entropy over the top-40 pool.

NO_PREFERENCE marks a attribute permanently consumed — never re-asked.
All modes degrade gracefully; the core interface stays positional:
decide(state, candidates, turn) with an optional context dict.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Optional

from neeshops.conversation.constraints import value_from_row
from neeshops.conversation.pseudo_attributes import row_value
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
    "feature": "Anything else it must have — a feature or detail that matters?",
    "other": "To narrow this down — what matters most right now? You can name two things, for example 'black; cotton'.",
}

# Attributes worth asking, ordered by expected answerability. The
# evaluator's customer classifies card values via classify_constraint,
# which NEVER returns "brand" or "category" — asking those is always a
# wasted turn, so they are excluded here. Budget sits last: its card slot
# is competitive (only the first four cleaned card values are ever
# disclosed), so it's asked only after likelier fields.
_ASKABLE_FIELDS = ("material", "color", "style", "size", "feature", "use_case", "budget")

# When no evidence-backed field scores (all consumed/homogeneous/unknown),
# drain the catch-all fields — card leftovers ("Imported", a use) land here.
_CATCH_ALL_FIELDS = ("feature", "use_case", "budget")

_AGREEMENT_SHARE = 0.9
_AGREEMENT_MIN_POOL = 5


class ClarificationEngine:
    def __init__(
        self,
        strategy: Optional[dict[str, Any]] = None,
        catalog_lookup: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        self._cfg = (strategy or load_strategy())["clarification"]
        self._catalog_lookup = catalog_lookup or {}
        self._value_cache: dict[tuple[str, str], str] = {}

    # -- decision ------------------------------------------------------------

    def decide(
        self,
        state: ConversationState,
        candidates: list[Any],
        turn: int,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Return {"ask_attribute", "question", "should_recommend",
        "inferred", "gate"}.

        `ask_attribute`/`question` are None when there's nothing useful left
        to ask (budget spent, turn guard, small pool, confident pool, or
        every field is known/no-preference). `inferred` carries attribute
        values the top-10 pool agreed on (bonus-only, applied by the state
        manager). `gate` names the gate that produced the decision, for the
        instrumentation panel.
        """
        context = context or {}
        candidate_count = len(candidates)
        # Count real questions from history — asked_attributes is deduplicated
        # and would never exhaust the budget when one attribute repeats.
        questions_asked = sum(1 for t in state.history if t.asked_attribute)
        budget_left = questions_asked < self._cfg["max_questions_per_session"]

        decision: dict[str, Any] = {
            "ask_attribute": None,
            "question": None,
            "should_recommend": candidate_count > 0,
            "inferred": {},
            "gate": None,
        }
        inferred: dict[str, Any] = {}

        if not budget_left:
            decision["gate"] = "exhausted"
            return decision
        if turn > int(self._cfg.get("last_question_turn", 9)):
            # Turn guard: the only zero-score failure mode is exceeding 10
            # turns — structurally unreachable when questions stop here and
            # every turn still carries recommendations.
            decision["gate"] = "turn_guard"
            return decision
        if candidate_count < int(self._cfg.get("min_candidates_before_recommend", 10)):
            decision["gate"] = "small_pool"
            return decision
        if self._is_confident(context):
            decision["gate"] = "confident"
            return decision
        if self._wildcard_available(state):
            decision["ask_attribute"] = "other"
            decision["question"] = _QUESTIONS["other"]
            decision["gate"] = "wildcard"
            return decision

        if self._is_over_general(candidate_count, context):
            decision["gate"] = "over_generality"
        else:
            decision["gate"] = "entropy"

        field = self._select_attribute(state, candidates, context, inferred)
        if field is None:
            decision["gate"] = "no_field"
            decision["inferred"] = inferred
            return decision
        decision["ask_attribute"] = field
        decision["question"] = self._question_for(field, candidates)
        decision["inferred"] = inferred
        return decision

    # -- gates ----------------------------------------------------------------

    def _is_confident(self, context: dict[str, Any]) -> bool:
        """Top-10 all full-coverage AND a clear rank-1 margin → recommend."""
        ranked = context.get("ranked") or []
        scores = context.get("ranked_scores") or []
        token_index = context.get("token_index")
        groups = context.get("groups") or []
        if len(ranked) < 10 or len(scores) < 2 or not token_index or not groups:
            return False
        if not all(token_index.full_coverage(asin, groups) for asin in ranked[:10]):
            return False
        top, second = scores[0], scores[1]
        if top <= 0:
            return False
        return (top - second) / top >= float(self._cfg.get("margin_stop", 0.15))

    def _is_over_general(self, candidate_count: int, context: dict[str, Any]) -> bool:
        if context.get("over_generality"):
            return True
        # No constraints at all and the pool is already maxed out — the
        # retrieval breadth is saturated; ask before ranking noise.
        limit = int(context.get("candidate_limit", 0) or 0)
        groups = context.get("groups") or []
        return not groups and limit > 0 and candidate_count >= limit

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

    # -- attribute selection ---------------------------------------------------

    def _select_attribute(
        self,
        state: ConversationState,
        candidates: list[Any],
        context: dict[str, Any],
        inferred_out: dict[str, Any],
    ) -> Optional[str]:
        """Most informative unset attribute, agreement-inferred fields
        skipped (recorded instead), or None if nothing qualifies."""
        rows, weights, row_asins = self._entropy_rows(candidates, context)
        if not rows:
            return None if self._catalog_lookup else self._next_missing_field(state)
        token_index = context.get("token_index")
        agreement_rows = self._agreement_rows(context)

        scored: list[tuple[float, float, int, str]] = []
        for field in _ASKABLE_FIELDS:
            if not state.is_unset(field) or field in state.asked_attributes:
                continue
            if agreement_rows:
                agreed = self._agreed_value(field, agreement_rows)
                if agreed is not None:
                    inferred_out[field] = agreed
                    continue
            result = self._field_score(field, rows, weights, row_asins, token_index)
            if result is None:
                continue
            entropy, reduction = result
            scored.append((-entropy, reduction, CONSTRAINT_FIELDS.index(field), field))
        if scored:
            return min(scored)[3]
        # No evidence-backed field can split the pool — drain the catch-all
        # fields so the customer's remaining card values still get harvested.
        for field in _CATCH_ALL_FIELDS:
            if state.is_unset(field) and field not in state.asked_attributes:
                return field
        return None if self._catalog_lookup else self._next_missing_field(state)

    def _entropy_rows(
        self, candidates: list[Any], context: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[float], list[str]]:
        """Rows to compute entropy over: the plausible AND set (uniform —
        every plausible target is equally likely) when available, else the
        rank-weighted top-40 pool. Large plausible sets are stride-sampled
        (deterministically) to the row cap — the value distribution of a
        uniform sample is representative, and the cost stays bounded."""
        limit = int(self._cfg.get("entropy_plausible_limit", 20000))
        row_cap = int(self._cfg.get("entropy_row_cap", 1500))
        plausible_ids = context.get("plausible_ids") or []
        if context.get("token_index") and plausible_ids and len(plausible_ids) <= limit:
            asins = [a for a in plausible_ids if a in self._catalog_lookup]
            if row_cap and len(asins) > row_cap:
                step = (len(asins) + row_cap - 1) // row_cap
                asins = asins[::step]
            rows = [self._catalog_lookup[a] for a in asins]
            return rows, [1.0] * len(rows), asins
        top = candidates[: int(self._cfg.get("entropy_top_k", 40))]
        asins = [c.parent_asin for c in top if c.parent_asin in self._catalog_lookup]
        rows = [self._catalog_lookup[a] for a in asins]
        weights = [1.0 / (60.0 + i + 1.0) for i in range(len(rows))]
        return rows, weights, asins

    def _agreement_rows(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        ranked = context.get("ranked") or []
        if not self._catalog_lookup:
            return []
        return [
            self._catalog_lookup[a] for a in ranked[:10] if a in self._catalog_lookup
        ]

    def _agreed_value(self, field: str, rows: list[dict[str, Any]]) -> Optional[str]:
        """Value the top-10 pool agrees on (≥90% share, enough rows), or
        None. Agreement becomes an inferred slot — a bonus-only ranking
        signal — instead of a wasted question."""
        if len(rows) < _AGREEMENT_MIN_POOL:
            return None
        values = [v for v in (self._value(field, row) for row in rows) if v]
        if len(values) < _AGREEMENT_MIN_POOL:
            return None
        top_value, count = Counter(values).most_common(1)[0]
        if count / len(values) >= _AGREEMENT_SHARE:
            return top_value
        return None

    def _field_score(
        self,
        field: str,
        rows: list[dict[str, Any]],
        weights: list[float],
        row_asins: list[str],
        token_index: Any,
    ) -> Optional[tuple[float, float]]:
        """(entropy, expected-remaining-fraction) for one field, or None."""
        dist: dict[str, float] = {}
        for row, weight in zip(rows, weights):
            value = self._value(field, row)
            if not value:
                continue
            dist[value] = dist.get(value, 0.0) + weight
        if len(dist) < 2:
            return None
        total = sum(dist.values())
        if total <= 0:
            return None
        if max(dist.values()) / total > 0.9:
            return None  # pool already homogeneous on this field
        entropy = -sum(
            (w / total) * math.log(w / total) for w in dist.values()
        )
        reduction = self._expected_remaining(
            dist, total, row_asins, token_index
        )
        return entropy, reduction

    def _expected_remaining(
        self,
        dist: dict[str, float],
        total: float,
        row_asins: list[str],
        token_index: Any,
    ) -> float:
        """Expected fraction of the plausible set that would REMAIN if the
        user answered this attribute — the tie-breaker for "which question
        best splits the set of items that could still be the target"."""
        if token_index is None or not row_asins or len(row_asins) > 1000:
            return 1.0
        from neeshops.retrieval.token_index import index_tokenize

        rows_total = len(row_asins)
        acc = 0.0
        for value, weight in dist.items():
            tokens = index_tokenize(value)
            if not tokens:
                continue
            count = sum(
                1
                for asin in row_asins
                if token_index.full_coverage(asin, [set(tokens)])
            )
            acc += (weight / total) * (count / rows_total)
        return acc

    def _value(self, field: str, row: dict[str, Any]) -> str:
        """Cached value evidence for one (field, row): the curated
        extractor's answer, else a mined pseudo-attribute term (the
        data/pseudo_attributes.json sidecar — evidence only, never a
        filter). Rows without an asin (synthetic test rows) bypass the
        cache."""
        asin = str(row.get("parent_asin") or "")
        if not asin:
            return value_from_row(field, row) or ""
        key = (field, asin)
        if key not in self._value_cache:
            value = value_from_row(field, row)
            if not value:
                value = row_value(field, row) or ""
            self._value_cache[key] = value
        return self._value_cache[key]

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
