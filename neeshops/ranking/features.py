"""Deterministic, inspectable feature extraction for local ranking."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from neeshops.models.session import NO_PREFERENCE, ConversationState
from neeshops.personalization.profile import personalization_boost
from neeshops.retrieval.base import Candidate
from neeshops.utils.tokens import tokenize


class MatchStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


# These state slots represent explicit, objectively checkable requirements.
# Style, feature, and use_case stay soft because catalog text for them is
# descriptive and incomplete rather than a reliable controlled attribute.
HARD_CONSTRAINT_FIELDS = ("category", "color", "material", "size", "brand", "budget")
SOFT_CONSTRAINT_FIELDS = ("style", "feature", "use_case")


@dataclass(frozen=True)
class ConstraintEvaluation:
    statuses: Mapping[str, MatchStatus] = field(default_factory=dict)
    hard_violations: tuple[str, ...] = ()
    soft_matches: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankingFeatures:
    retrieval_score_normalized: float
    retrieval_rank: int
    category_match: float
    title_overlap: float
    feature_overlap: float
    color_match: float
    material_match: float
    brand_match: float
    style_match: float
    size_match: float
    budget_fit: float
    hard_constraint_violation_count: int
    personalization_boost: float


class RankingFeatureExtractor:
    """Extract deterministic features without mutating candidate or state."""

    def extract(
        self,
        candidate: Candidate,
        row: Mapping[str, Any],
        state: ConversationState,
        *,
        retrieval_rank: int,
        retrieval_score_normalized: float,
    ) -> tuple[RankingFeatures, ConstraintEvaluation]:
        constraints = _meaningful_constraints(state)
        statuses: dict[str, MatchStatus] = {}

        for field_name in HARD_CONSTRAINT_FIELDS:
            if field_name not in constraints:
                continue
            if field_name == "budget":
                statuses[field_name] = _budget_status(constraints[field_name], row.get("price"))
            else:
                statuses[field_name] = _attribute_status(
                    constraints[field_name],
                    _attribute_values(field_name, row),
                    _supporting_values(field_name, row),
                )

        for field_name in SOFT_CONSTRAINT_FIELDS:
            if field_name in constraints:
                statuses[field_name] = _soft_status(field_name, constraints[field_name], row)

        hard_violations = tuple(
            field_name
            for field_name in HARD_CONSTRAINT_FIELDS
            if statuses.get(field_name) is MatchStatus.MISMATCH
        )
        soft_matches = tuple(
            field_name
            for field_name in SOFT_CONSTRAINT_FIELDS
            if statuses.get(field_name) is MatchStatus.MATCH
        )
        evaluation = ConstraintEvaluation(statuses, hard_violations, soft_matches)

        intent_tokens = _constraint_tokens(constraints)
        title_tokens = set(tokenize(_text(row.get("title"))))
        feature_tokens = set(tokenize(_join_values(row.get("features"))))

        features = RankingFeatures(
            retrieval_score_normalized=_finite_or_zero(retrieval_score_normalized),
            retrieval_rank=retrieval_rank,
            category_match=_match_value(statuses.get("category")),
            title_overlap=_overlap(intent_tokens, title_tokens),
            feature_overlap=_overlap(intent_tokens, feature_tokens),
            color_match=_match_value(statuses.get("color")),
            material_match=_match_value(statuses.get("material")),
            brand_match=_match_value(statuses.get("brand")),
            style_match=_match_value(statuses.get("style")),
            size_match=_match_value(statuses.get("size")),
            budget_fit=_match_value(statuses.get("budget")),
            hard_constraint_violation_count=len(hard_violations),
            personalization_boost=personalization_boost(dict(row), state.user_profile),
        )
        return features, evaluation


def _meaningful_constraints(state: ConversationState) -> dict[str, Any]:
    return {
        key: value
        for key, value in state.constraints.items()
        if value is not None and value != NO_PREFERENCE and _has_value(value)
    }


def _has_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _attribute_values(field_name: str, row: Mapping[str, Any]) -> tuple[str, ...]:
    if field_name == "category":
        return _values(row.get("category"), row.get("categories"))
    if field_name == "brand":
        return _values(row.get("brand"), row.get("store"))
    return _values(row.get(field_name))


def _supporting_values(field_name: str, row: Mapping[str, Any]) -> tuple[str, ...]:
    if field_name == "category":
        return ()
    if field_name == "brand":
        return _values(row.get("title"))
    return _values(row.get("title"), row.get("features"), row.get("description"), row.get("details"))


def _attribute_status(
    required: Any, observed: tuple[str, ...], supporting: tuple[str, ...] = ()
) -> MatchStatus:
    required_tokens = set(tokenize(_join_values(required)))
    if not required_tokens:
        return MatchStatus.UNKNOWN
    if observed:
        observed_tokens = set(tokenize(" ".join(observed)))
        return MatchStatus.MATCH if required_tokens <= observed_tokens else MatchStatus.MISMATCH
    supporting_tokens = set(tokenize(" ".join(supporting)))
    if required_tokens <= supporting_tokens:
        return MatchStatus.MATCH
    return MatchStatus.UNKNOWN


def _soft_status(field_name: str, required: Any, row: Mapping[str, Any]) -> MatchStatus:
    direct = _values(row.get(field_name))
    text = direct or _values(row.get("title"), row.get("features"), row.get("description"))
    if not text:
        return MatchStatus.UNKNOWN
    required_tokens = set(tokenize(_join_values(required)))
    observed_tokens = set(tokenize(" ".join(text)))
    if not required_tokens:
        return MatchStatus.UNKNOWN
    return MatchStatus.MATCH if required_tokens <= observed_tokens else MatchStatus.UNKNOWN


def _budget_status(required: Any, price: Any) -> MatchStatus:
    budget = _number(required)
    product_price = _number(price)
    if budget is None or product_price is None:
        return MatchStatus.UNKNOWN
    return MatchStatus.MATCH if product_price <= budget else MatchStatus.MISMATCH


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _constraint_tokens(constraints: Mapping[str, Any]) -> set[str]:
    values = [value for key, value in constraints.items() if key != "budget"]
    return set(tokenize(" ".join(_join_values(value) for value in values)))


def _overlap(intent_tokens: set[str], product_tokens: set[str]) -> float:
    if not intent_tokens or not product_tokens:
        return 0.0
    return len(intent_tokens & product_tokens) / len(intent_tokens)


def _match_value(status: MatchStatus | None) -> float:
    return 1.0 if status is MatchStatus.MATCH else 0.0


def _values(*values: Any) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        items: Iterable[Any] = value if isinstance(value, (list, tuple, set)) else (value,)
        out.extend(text for item in items if (text := _text(item)).strip())
    return tuple(out)


def _join_values(value: Any) -> str:
    return " ".join(_values(value))


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value or "")


def _finite_or_zero(value: Any) -> float:
    number = _number(value)
    return number if number is not None else 0.0
