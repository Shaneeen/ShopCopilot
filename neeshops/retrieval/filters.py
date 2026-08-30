"""Metadata filtering: narrow a candidate list by structured constraints
(category, budget, material, color, brand, size, style) using whatever the
real catalog schema actually provides.

The official catalog (`docs/DATA_ATTRIBUTION.md`, `evaluator/
local_evaluator.py::searchable_text`) does not carry flat `color`/
`material`/`brand` fields — that information, where present at all, is
buried inside free-text `title`/`features`/`details`/`description`. So most
constraints are evaluated as a soft text-containment check across those
fields rather than an exact structured match.

Demote, don't drop (default `apply_filters` pipeline): every constraint the
simulator discloses is verbatim from the *target* product's own text, so a
hard text filter can delete the very product the user is describing just
because its sparse metadata never spells the attribute out. Instead:

1. `budget` is the only true hard drop (structured `price`), and even it
   tolerates `filters.budget_tolerance` — "budget around $27.99" must not
   kill a $29.99 target.
2. `category` hard-drops only while at least `filters.min_pool_keep`
   candidates survive; below that it counts as a soft miss instead, so a
   wrong or fake category claim can't empty the pool.
3. All text constraints never drop: candidates with fewer unsatisfied
   constraints are ordered first (stable by retrieval rank), so
   constraint matches fill the ranker's rerank window. The ranker
   (ranking/features.py) adds the per-constraint match bonuses on top.

Applied *after* retrieval, before ranking — see neeshops/agent.py. Any
product without enough information to evaluate a constraint stays in the
pool (fail open) rather than being punished for sparse metadata.
"""
from __future__ import annotations

from typing import Any, Callable

from neeshops.config.settings import load_strategy
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate
from neeshops.retrieval.token_index import index_tokenize
from neeshops.utils.tokens import tokenize

FilterFn = Callable[[dict[str, Any], ConversationState], bool]

_TEXT_FIELDS = ("title", "categories", "features", "details", "description", "store")

# Constraints evaluated as soft text containment in the default pipeline.
_SOFT_FIELDS = ("color", "material", "brand", "size", "style", "feature", "use_case")


def _strategy_filters() -> dict[str, Any]:
    try:
        return load_strategy().get("filters", {})
    except Exception:  # pragma: no cover - misconfigured settings fail open
        return {}


def _budget_tolerance() -> float:
    raw = _strategy_filters().get("budget_tolerance", 1.10)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 1.10


def _min_pool_keep() -> int:
    raw = _strategy_filters().get("min_pool_keep", 10)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 10


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
        return price is None or float(price) <= float(budget) * _budget_tolerance()
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


def _text_satisfies(value: Any, product_row: dict[str, Any]) -> bool:
    """Soft containment check for a constraint value across the product's
    text fields. Multi-word values match when every token appears
    (order-independent), so slot-filled phrases like "machine wash;
    imported" don't fail on word order."""
    text = _product_text(product_row)
    if not text:
        return True
    value_text = str(value).lower()
    tokens = [t for t in tokenize(value_text) if len(t) >= 2]
    if len(tokens) > 1:
        return all(t in text for t in tokens)
    return value_text in text


def _tokens_satisfy(value: Any, asin: str, token_index: Any) -> bool:
    """Fast path: O(1) membership checks against the precomputed doc token
    set (see retrieval/token_index.py). Same all-tokens-must-appear
    semantics as the legacy check on the token level; unknown ASINs fail
    open like missing rows. Constraint values are verbatim product tokens
    (pre-cleaned inputs), so exact token matching is the correct semantics.
    """
    doc_tokens = token_index.doc_tokens(asin)
    if doc_tokens is None:
        return True
    tokens = index_tokenize(value)
    if not tokens:
        return True
    return all(t in doc_tokens for t in tokens)


def text_contains_filter(field: str) -> FilterFn:
    """Legacy single-constraint filter kept for explicit filter lists and
    unit tests — passes when `field`'s constraint value appears across the
    product's text fields, or when there's nothing to check against."""

    def _filter(product_row: dict[str, Any], state: ConversationState) -> bool:
        value = state.constraint_value(field)
        if value is None or state.has_no_preference(field):
            return True
        return _text_satisfies(value, product_row)

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


def _soft_constraint_values(state: ConversationState) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for field in _SOFT_FIELDS:
        value = state.constraint_value(field)
        if value is None or state.has_no_preference(field):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out.append((field, value))
    return out


def apply_filters(
    candidates: list[Candidate],
    catalog_lookup: dict[str, dict[str, Any]],
    state: ConversationState,
    filters: list[FilterFn] | None = None,
    token_index: Any | None = None,
) -> list[Candidate]:
    """Narrow/order candidates by the conversation's constraints.

    `filters=None` (production default) runs the demote-not-drop pipeline
    described in the module docstring. An explicit `filters` list runs
    those functions as classic hard filters (fail-open on missing lookup
    rows), kept for experiments and unit tests.

    `token_index` (optional) switches Pass 3's per-candidate text checks to
    O(1) token-set membership against the precomputed index instead of
    re-flattening full product text every turn. Same semantics, ~1000x
    fewer string scans.
    """
    if filters is not None:
        out = []
        for c in candidates:
            row = catalog_lookup.get(c.parent_asin)
            if row is None or all(f(row, state) for f in filters):
                out.append(c)
        return out

    soft_values = _soft_constraint_values(state)

    def _text_ok(asin: str, row: dict[str, Any], value: Any) -> bool:
        if token_index is not None:
            return _tokens_satisfy(value, asin, token_index)
        return _text_satisfies(value, row)

    # Pass 1: budget is the only structured hard drop.
    budgeted: list[tuple[int, Candidate, dict[str, Any] | None]] = []
    for idx, c in enumerate(candidates):
        row = catalog_lookup.get(c.parent_asin)
        if row is not None and not budget_filter(row, state):
            continue
        budgeted.append((idx, c, row))
    if not budgeted:
        return []

    # Pass 2: category hard-drops only while enough candidates survive.
    categorized = [
        (idx, c, row)
        for idx, c, row in budgeted
        if row is None or category_filter(row, state)
    ]
    hard_category = len(categorized) >= _min_pool_keep()
    pool = categorized if hard_category else budgeted

    # Pass 3: text constraints demote, never drop — fewer misses first,
    # stable by original retrieval rank.
    scored: list[tuple[int, int, Candidate]] = []
    for idx, c, row in pool:
        misses = 0
        if row is None:
            scored.append((0, idx, c))
            continue
        if not hard_category and not category_filter(row, state):
            misses += 1
        for _field, value in soft_values:
            if not _text_ok(c.parent_asin, row, value):
                misses += 1
        scored.append((misses, idx, c))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [c for _, _, c in scored]
