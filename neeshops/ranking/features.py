"""Deterministic, inspectable feature extraction for local ranking."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from neeshops.models.session import NO_PREFERENCE, ConversationState
from neeshops.personalization.profile import personalization_boost
from neeshops.retrieval.base import Candidate
from neeshops.retrieval.token_index import FIELD_SALIENCE, constraint_token_groups, index_tokenize
from neeshops.utils.tokens import tokenize

# Weight of stale (erased) constraint groups in coverage — mirrors
# conversation.state.STALE_SLOT_WEIGHT / config intent.route_flip_erase_weight.
STALE_GROUP_WEIGHT = 0.3


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
    coverage: float = 0.0
    """IDF-weighted fraction of active constraint groups satisfied (stale
    groups count at 0.3) — the primary twin tie-breaker."""
    salience: float = 0.0
    """Mean field salience of the satisfied constraints (title beats store)."""
    popularity: float = 0.0
    """Normalized popularity (rating × log1p reviews), browsing bump input."""
    inferred_boost: float = 0.0
    """Agreement-inferred attribute matches × their decayed weight."""
    active_constraint_count: int = 0
    """Count of explicit, non-empty constraint slots this turn. With very
    few active constraints (typically browsing's single generic category),
    title/feature overlap are near-duplicates of that one constraint rather
    than independent evidence — see ConstraintAwareRanker's overlap
    dampening, gated on this count."""


class RankingFeatureExtractor:
    """Extract deterministic features without mutating candidate or state."""

    def __init__(
        self,
        budget_tolerance: float = 1.0,
        token_index: Any = None,
    ) -> None:
        # >1.0 keeps products marginally above "budget around $X"-style soft
        # caps in the MATCH tier instead of marking them as violations.
        self._budget_tolerance = float(budget_tolerance)
        self._token_index = token_index

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
                statuses[field_name] = _budget_status(
                    constraints[field_name], row.get("price"), self._budget_tolerance
                )
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

        coverage, salience = self._coverage_and_salience(candidate.parent_asin, row, state)
        popularity = self._popularity(candidate.parent_asin)
        inferred_boost = self._inferred_boost(candidate.parent_asin, row, state)

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
            coverage=coverage,
            salience=salience,
            popularity=popularity,
            inferred_boost=inferred_boost,
            active_constraint_count=len(constraints),
        )
        return features, evaluation

    # -- coverage × IDF × salience ------------------------------------------

    def _coverage_and_salience(
        self, asin: str, row: Mapping[str, Any], state: ConversationState
    ) -> tuple[float, float]:
        """coverage = Σ w·idf·[group satisfied] / Σ w·idf over active
        constraint groups (weight 1.0) and stale groups (weight 0.3 — weak
        signal after an intent override, never a demotion). Salience is the
        mean best-field salience of the SATISFIED active constraints."""
        active = constraint_token_groups(state.constraints)
        stale_map = getattr(state, "stale", None) or {}
        stale = constraint_token_groups(stale_map)
        if not active and not stale:
            return 0.0, 0.0

        doc_tokens: Optional[frozenset[str]]
        if self._token_index is not None:
            doc_tokens = self._token_index.doc_tokens(asin)
        else:
            doc_tokens = None
        row_tokens = _row_token_sets(row)

        groups = active + stale
        weights = [1.0] * len(active) + [STALE_GROUP_WEIGHT] * len(stale)
        if self._token_index is not None:
            coverage = self._token_index.group_coverage(asin, groups, weights)
        else:
            numerator = denominator = 0.0
            for group, weight in zip(groups, weights):
                idf = max((self._token_index_idf(t) for t in group), default=0.0)
                denominator += weight * idf
                if any(t in row_tokens.get("all", frozenset()) for t in group):
                    numerator += weight * idf
            coverage = numerator / denominator if denominator > 0 else 0.0

        satisfied_salience: list[float] = []
        # Field → constraint-value mapping for salience (active only).
        for field, value in state.constraints.items():
            if field == "budget" or value is None or value == NO_PREFERENCE:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            tokens = frozenset(index_tokenize(value))
            if not tokens:
                continue
            if doc_tokens is not None:
                satisfied = tokens <= doc_tokens
            else:
                satisfied = tokens <= row_tokens.get("all", frozenset())
            if satisfied:
                satisfied_salience.append(_field_salience(tokens, row_tokens))
        salience = (
            sum(satisfied_salience) / len(satisfied_salience)
            if satisfied_salience
            else 0.0
        )
        return coverage, salience

    def _token_index_idf(self, token: str) -> float:
        if self._token_index is None:
            return 1.0
        return self._token_index.idf(token)

    def _popularity(self, asin: str) -> float:
        if self._token_index is None:
            return 0.0
        return self._token_index.popularity(asin)

    def _inferred_boost(
        self, asin: str, row: Mapping[str, Any], state: ConversationState
    ) -> float:
        inferred = getattr(state, "inferred", None) or {}
        if not inferred:
            return 0.0
        if self._token_index is not None:
            doc = self._token_index.doc_tokens(asin)
            if doc is None:
                return 0.0
        else:
            doc = frozenset(_row_token_sets(row).get("all", frozenset()))
        boosts = [
            slot.weight
            for slot in inferred.values()
            if slot.value is not None
            and frozenset(index_tokenize(slot.value)) <= doc
        ]
        return sum(boosts) / len(inferred) if boosts else 0.0


def _meaningful_constraints(state: ConversationState) -> dict[str, Any]:
    return {
        key: value
        for key, value in state.constraints.items()
        if value is not None and value != NO_PREFERENCE and _has_value(value)
    }


_ROW_FIELDS = tuple(field for field, _ in FIELD_SALIENCE)


def _row_token_sets(row: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Per-field token sets (plus an "all" union) — the no-index fallback
    for coverage/salience/inferred checks and the salience lookup."""
    out: dict[str, frozenset[str]] = {}
    union: set[str] = set()
    for field_name in _ROW_FIELDS:
        tokens = frozenset(tokenize(_join_values(row.get(field_name))))
        out[field_name] = tokens
        union.update(tokens)
    out["all"] = frozenset(union)
    return out


def _field_salience(
    tokens: frozenset[str], row_tokens: Mapping[str, frozenset[str]]
) -> float:
    """Salience of the highest-ranked field containing ALL the tokens."""
    for field_name, salience in FIELD_SALIENCE:
        if tokens <= row_tokens.get(field_name, frozenset()):
            return salience
    return 0.0


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


def _budget_status(required: Any, price: Any, tolerance: float = 1.0) -> MatchStatus:
    budget = _number(required)
    product_price = _number(price)
    if budget is None or product_price is None:
        return MatchStatus.UNKNOWN
    return MatchStatus.MATCH if product_price <= budget * tolerance else MatchStatus.MISMATCH


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
