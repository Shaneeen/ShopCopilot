"""Metadata filtering: narrow a candidate list by structured constraints
(category, budget, material, color, brand, size, style) using whatever the
real catalog schema actually provides.

The official catalog (`docs/DATA_ATTRIBUTION.md`, `evaluator/
local_evaluator.py::searchable_text`) does not carry flat `color`/
`material`/`brand` fields — that information, where present at all, is
buried inside free-text `title`/`features`/`details`/`description`. So
most constraints here are applied as a soft text-containment check across
those fields rather than an exact structured match; only `budget`
(against the real `price` field) and `category` (against the real
`categories` list) are closer to a true structured filter.

Applied *after* retrieval, before/alongside ranking — see
neeshops/agent.py. A constraint filter is deliberately fail-open: any
product without enough information to evaluate a constraint stays in the
candidate pool rather than being punished for sparse metadata.
"""
from __future__ import annotations

from typing import Any, Callable

from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate
from neeshops.utils.tokens import tokenize

FilterFn = Callable[[dict[str, Any], ConversationState], bool]

_TEXT_FIELDS = ("title", "categories", "features", "details", "description", "store")


def _product_text(product_row: dict[str, Any]) -> str:
    parts = []
    for field in _TEXT_FIELDS:
        value = product_row.get(field)
        if isinstance(value, dict):
            parts.extend(f"{k} {v}" for k, v in value.items())
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).lower()


def budget_filter(product_row: dict[str, Any], state: ConversationState) -> bool:
    budget = state.constraint_value("budget")
    if budget is None or state.has_no_preference("budget"):
        return True
    try:
        price = product_row.get("price")
        return price is None or float(price) <= float(budget)
    except (TypeError, ValueError):
        # Unparseable price (the real catalog has a few junk string values) —
        # fail open, same as missing data.
        return True


def category_filter(product_row: dict[str, Any], state: ConversationState) -> bool:
    value = state.constraint_value("category")
    if value is None or state.has_no_preference("category"):
        return True
    categories = product_row.get("categories")
    if not categories:
        return True  # fail open on sparse metadata
    categories_text = " ".join(str(c) for c in categories).lower()
    # Users name categories in their own words ("women shirts"); the catalog
    # stores breadcrumb paths ("Clothing, Shirts, T-Shirts"). Match on any
    # meaningful token rather than the raw phrase, which would self-filter
    # the very products the user is describing.
    tokens = [t for t in tokenize(str(value)) if len(t) >= 3]
    if not tokens:
        return True
    return any(t in categories_text for t in tokens)


def text_contains_filter(field: str) -> FilterFn:
    """Soft filter for constraints (material, color, brand, style, ...)
    that the real catalog doesn't expose as a discrete field — passes if
    the constraint value appears across the product's text fields, or if
    there's nothing to check against. Multi-word values match when every
    token appears (order-independent), so slot-filled phrases like
    "machine wash; imported" don't fail on word order."""

    def _filter(product_row: dict[str, Any], state: ConversationState) -> bool:
        value = state.constraint_value(field)
        if value is None or state.has_no_preference(field):
            return True
        text = _product_text(product_row)
        if not text:
            return True
        value_text = str(value).lower()
        tokens = [t for t in tokenize(value_text) if len(t) >= 2]
        if len(tokens) > 1:
            return all(t in text for t in tokens)
        return value_text in text

    return _filter


DEFAULT_FILTERS: list[FilterFn] = [
    budget_filter,
    category_filter,
    text_contains_filter("color"),
    text_contains_filter("material"),
    text_contains_filter("brand"),
    text_contains_filter("size"),
    text_contains_filter("style"),
    text_contains_filter("feature"),
    text_contains_filter("use_case"),
]


def apply_filters(
    candidates: list[Candidate],
    catalog_lookup: dict[str, dict[str, Any]],
    state: ConversationState,
    filters: list[FilterFn] | None = None,
) -> list[Candidate]:
    """Drop candidates whose catalog row fails any filter.

    `catalog_lookup` maps parent_asin -> raw catalog row; a candidate whose
    asin isn't in the lookup is passed through unfiltered (fail open, not
    closed — a missing lookup shouldn't silently empty the result set).
    """
    active_filters = filters or DEFAULT_FILTERS
    out = []
    for c in candidates:
        row = catalog_lookup.get(c.parent_asin)
        if row is None:
            out.append(c)
            continue
        if all(f(row, state) for f in active_filters):
            out.append(c)
    return out
