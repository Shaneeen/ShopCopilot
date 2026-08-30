"""In-memory Boolean token index over the frozen catalog.

The session simulator's constraint values are verbatim tokens from the
target product's own text fields, so the set of products containing ALL
active constraint tokens — a Boolean AND over an inverted index — contains
the target by construction. This module makes that set computable exactly:

- ``and_search``  — doc ids containing at least one token from EVERY group
  (a group is a set of interchangeable alternatives, e.g. a token plus its
  synonyms), optionally price-gated, fail-open on unparseable prices.
- ``and_search_backoff`` — greedy relaxation: while the AND set is empty,
  drop the group whose removal restores the largest set (bounded, logged).
  Dropped groups are returned so forensics can spot paraphrases. A price
  conflict is NOT a token problem: a non-empty raw set that the price gate
  empties returns empty WITHOUT dropping tokens.
- ``coverage_rank`` — partial-match ordering (most groups satisfied first,
  ties by popularity) used to pad the rerank window.
- ``doc_tokens`` / ``idf`` / ``popularity`` — shared lookup tables for the
  fast filter path and the coverage×IDF ranking features.

Fully in-memory (§4.3: no external vector DB); the catalog file itself is
never written. One tokenizer (``index_tokenize``) is applied to BOTH the
index side and every query/constraint side, so lookups are always
consistent. Inputs are pre-cleaned (no typos per the rules), so exact
token matching is the correct semantics — no fuzzy matching anywhere.
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

from neeshops.models.session import NO_PREFERENCE
from neeshops.retrieval.bm25 import _SEARCH_FIELDS, _flatten
from neeshops.utils.logging import log_event

_INDEX_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Field salience for ranking features (high → the constraint token appears
# in a field users actually read). Consumed by ranking/features.py.
FIELD_SALIENCE: tuple[tuple[str, float], ...] = (
    ("title", 1.0),
    ("features", 0.85),
    ("categories", 0.7),
    ("details", 0.55),
    ("description", 0.5),
    ("store", 0.35),
)

# Curated synonym groups — retrieval-only expansion, NEVER a hard filter.
# Populated from scripts/pool_miss_forensics.py output (paraphrase offenders).
SYNONYMS: dict[str, tuple[str, ...]] = {}


def index_tokenize(value: Any) -> list[str]:
    """Tokenizer used identically on the index side and the query side.

    Lowercase, split on non-alphanumerics, keep tokens of length >= 2
    (sizes like "xl" and "10" survive — dropping them silently loses
    recall), light plural stem (shoes→shoe, skipping ss/us/is).
    """
    out: list[str] = []
    for raw in _INDEX_TOKEN_RE.findall(str(value).lower()):
        if len(raw) < 2:
            continue
        if len(raw) > 3 and raw.endswith("s") and not raw.endswith(("ss", "us", "is")):
            raw = raw[:-1]
        out.append(raw)
    return out


def constraint_token_groups(
    constraints: dict[str, Any],
    exclude_fields: tuple[str, ...] = ("budget", "other"),
) -> list[set[str]]:
    """Active constraint values → list of token groups for the AND search.

    Each constraint value becomes one group (all its tokens must be
    present); a token with synonyms widens its group — the product needs
    only ONE member of the group per constraint value. NO_PREFERENCE,
    blanks, budget (numeric, not text) and the wildcard slot are skipped.
    """
    groups: list[set[str]] = []
    for field, value in constraints.items():
        if field in exclude_fields or value is None:
            continue
        if value == NO_PREFERENCE:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        tokens = index_tokenize(value)
        if not tokens:
            continue
        group: set[str] = set()
        for token in tokens:
            group.add(token)
            group.update(SYNONYMS.get(token, ()))
        groups.append(group)
    return groups


def parse_price(value: Any) -> Optional[float]:
    """Parse a catalog price; junk strings → None (fail-open everywhere)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class TokenIndex:
    """Boolean inverted index + shared per-doc lookup tables."""

    def __init__(self, catalog_lookup: dict[str, dict[str, Any]]) -> None:
        started = time.perf_counter()
        asins: list[str] = list(catalog_lookup.keys())
        self._asins = asins
        n_docs = len(asins)
        self._n_docs = n_docs

        doc_tokens: dict[str, frozenset[str]] = {}
        postings: dict[str, list[int]] = {}
        prices = np.full(n_docs, np.nan, dtype=np.float64)
        pop_raw = np.zeros(n_docs, dtype=np.float64)

        for doc_id, asin in enumerate(asins):
            row = catalog_lookup[asin]
            tokens = index_tokenize(_doc_text(row))
            frozen = frozenset(tokens)
            doc_tokens[asin] = frozen
            for token in frozen:
                postings.setdefault(token, []).append(doc_id)
            price = parse_price(row.get("price"))
            if price is not None:
                prices[doc_id] = price
            rating = parse_price(row.get("average_rating")) or 0.0
            reviews = parse_price(row.get("rating_number")) or 0.0
            pop_raw[doc_id] = rating * math.log1p(max(reviews, 0.0))

        self._doc_tokens = doc_tokens
        self._postings = {
            token: np.array(doc_ids, dtype=np.int32)
            for token, doc_ids in postings.items()
        }
        self._idf = {
            token: math.log(n_docs / len(ids))
            for token, ids in self._postings.items()
        }
        self._prices = prices
        if n_docs and pop_raw.max() > pop_raw.min():
            self._popularity = (pop_raw - pop_raw.min()) / (pop_raw.max() - pop_raw.min())
        else:
            self._popularity = np.zeros(n_docs, dtype=np.float64)
        self._asin_pos = {asin: i for i, asin in enumerate(asins)}
        self._max_idf = math.log(max(n_docs, 2))
        log_event(
            "token_index.built",
            docs=n_docs,
            terms=len(self._postings),
            seconds=round(time.perf_counter() - started, 2),
        )

    # -- lookups ------------------------------------------------------------

    def doc_tokens(self, asin: str) -> Optional[frozenset[str]]:
        return self._doc_tokens.get(asin)

    def idf(self, token: str) -> float:
        """IDF of a token; unseen tokens get max IDF (rarest possible)."""
        return self._idf.get(token, self._max_idf)

    def popularity(self, asin: str) -> float:
        pos = self._asin_pos.get(asin)
        return float(self._popularity[pos]) if pos is not None else 0.0

    def price(self, asin: str) -> Optional[float]:
        pos = self._asin_pos.get(asin)
        if pos is None:
            return None
        value = float(self._prices[pos])
        return None if math.isnan(value) else value

    # -- Boolean AND --------------------------------------------------------

    def _group_ids(self, group: set[str]) -> np.ndarray:
        """Doc ids containing ANY token of the group (sorted, unique)."""
        arrays = [self._postings[t] for t in group if t in self._postings]
        if not arrays:
            return np.empty(0, dtype=np.int32)
        if len(arrays) == 1:
            return arrays[0]
        return np.unique(np.concatenate(arrays))

    def _intersect_ids(self, groups: list[set[str]]) -> np.ndarray:
        if not groups:
            return np.empty(0, dtype=np.int32)
        ordered = sorted((self._group_ids(g) for g in groups), key=len)
        result = ordered[0]
        for ids in ordered[1:]:
            if len(result) == 0:
                break
            result = np.intersect1d(result, ids, assume_unique=True)
        return result

    def _price_filter(self, ids: np.ndarray, price_cap: Optional[float]) -> np.ndarray:
        """Keep ids with price ≤ cap; missing/unparseable prices pass."""
        if price_cap is None or not len(ids):
            return ids
        prices = self._prices[ids]
        return ids[np.isnan(prices) | (prices <= price_cap)]

    def and_search_groups(
        self, groups: list[set[str]], price_cap: Optional[float] = None
    ) -> list[str]:
        """Doc ids containing at least one token from EVERY group."""
        return [self._asins[i] for i in self._price_filter(self._intersect_ids(groups), price_cap)]

    def and_search(
        self, tokens: Iterable[str], price_cap: Optional[float] = None
    ) -> list[str]:
        return self.and_search_groups([{t} for t in set(tokens)], price_cap)

    def and_search_backoff(
        self,
        groups: list[set[str]],
        price_cap: Optional[float] = None,
        min_ids: int = 1,
        max_drops: Optional[int] = None,
    ) -> tuple[list[str], list[set[str]]]:
        """Greedy relaxation until the AND set has ≥ ``min_ids`` members.

        Fires only when the full AND set is EMPTY. A non-empty raw set that
        the price gate empties is a budget conflict, not a token problem —
        return empty WITHOUT dropping anything. Each round drops the single
        group whose removal restores the largest set; bounded by
        ``max_drops`` (default: leave at least one group). Returns
        ``(asins, dropped_groups)`` so callers can log/forensics them.
        """
        if not groups:
            return [], []
        raw_ids = self._intersect_ids(groups)
        if len(raw_ids) == 0:
            drops: list[set[str]] = []
            remaining = list(groups)
            budget = max_drops if max_drops is not None else max(len(groups) - 1, 0)
            while len(remaining) > 1 and len(drops) < budget:
                best_ids: np.ndarray = np.empty(0, dtype=np.int32)
                best_idx = -1
                for i in range(len(remaining)):
                    trial = remaining[:i] + remaining[i + 1 :]
                    ids = self._intersect_ids(trial)
                    if len(ids) > len(best_ids):
                        best_ids, best_idx = ids, i
                if best_idx < 0 or len(best_ids) == 0:
                    break
                drops.append(remaining.pop(best_idx))
                priced = self._price_filter(best_ids, price_cap)
                if len(priced) >= min_ids:
                    return [self._asins[i] for i in priced], drops
            priced = self._price_filter(self._intersect_ids(remaining), price_cap)
            if len(priced) >= min_ids:
                return [self._asins[i] for i in priced], drops
            return [], drops

        priced_ids = self._price_filter(raw_ids, price_cap)
        if len(priced_ids) >= min_ids:
            return [self._asins[i] for i in priced_ids], []
        # Price conflict (budget below everything matching the tokens) —
        # dropping constraint tokens would only lie about the user's intent.
        return [], []

    def set_size(self, groups: list[set[str]], price_cap: Optional[float] = None) -> int:
        return len(self.and_search_groups(groups, price_cap))

    def group_coverage(
        self,
        asin: str,
        groups: list[set[str]],
        group_weights: Optional[list[float]] = None,
    ) -> float:
        """IDF-weighted fraction of constraint groups whose tokens appear in
        the doc: coverage = Σ w·idf·[group ⊆ doc] / Σ w·idf. This is the
        ranking feature; per-group idf is the rarest (max-idf) alternative.
        Unknown asin → 0.0 (the caller decides how to treat it)."""
        doc = self._doc_tokens.get(asin)
        if doc is None or not groups:
            return 0.0
        numerator = denominator = 0.0
        for gi, group in enumerate(groups):
            weight = group_weights[gi] if group_weights else 1.0
            idf = max((self.idf(token) for token in group), default=0.0)
            denominator += weight * idf
            if any(token in doc for token in group):
                numerator += weight * idf
        return numerator / denominator if denominator > 0 else 0.0

    def full_coverage(self, asin: str, groups: list[set[str]]) -> bool:
        """True when EVERY constraint group is satisfied (coverage == 1.0)."""
        doc = self._doc_tokens.get(asin)
        if doc is None:
            return False
        return all(any(token in doc for token in group) for group in groups)

    # -- partial-match padding ----------------------------------------------

    def coverage_rank(
        self,
        groups: list[set[str]],
        price_cap: Optional[float] = None,
        limit: int = 200,
    ) -> list[str]:
        """Docs satisfying the most groups first, ties by popularity, then
        asin — deterministic partial-match ordering for pool padding."""
        if not groups or not limit:
            return []
        counts = np.zeros(self._n_docs, dtype=np.int32)
        for group in groups:
            ids = self._group_ids(group)
            if len(ids):
                counts[ids] += 1
        candidates = np.nonzero(counts)[0]
        if price_cap is not None:
            candidates = self._price_filter(candidates, price_cap)
        if not len(candidates):
            return []
        order = sorted(
            candidates,
            key=lambda i: (-int(counts[i]), -float(self._popularity[i]), self._asins[i]),
        )
        return [self._asins[i] for i in order[:limit]]


_SHARED_INDEXES: dict[str, TokenIndex] = {}


def get_or_build_index(
    catalog_lookup: dict[str, dict[str, Any]],
    catalog_path: Optional[Path] = None,
) -> Optional[TokenIndex]:
    """Build (or reuse) the index for a catalog. Sharing is keyed by the
    resolved catalog path — same file, same read-only index — so multiple
    agents in one process (e.g. the oracle eval's strategy arms) build once.
    No path → no sharing (synthetic test catalogs must never collide).
    """
    if not catalog_lookup:
        return None
    key = str(Path(catalog_path).resolve()) if catalog_path else ""
    if key:
        cached = _SHARED_INDEXES.get(key)
        if cached is not None and cached._n_docs == len(catalog_lookup):
            return cached
    index = TokenIndex(catalog_lookup)
    if key:
        _SHARED_INDEXES[key] = index
    return index


def _doc_text(row: dict[str, Any]) -> str:
    """Same flattened field definition as the BM25 index — one source of
    truth for what text a product "has"."""
    return " ".join(_flatten(row.get(field)) for field in _SEARCH_FIELDS)


def loads_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    """Standalone catalog loader for scripts (forensics/mining)."""
    lookup: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            asin = row.get("parent_asin")
            if asin:
                lookup[str(asin)] = row
    return lookup
