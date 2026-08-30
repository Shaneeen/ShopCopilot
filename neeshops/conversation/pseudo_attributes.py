"""Pseudo-attribute lexicons (P4): mined sidecar, never a catalog mutation.

`data/pseudo_attributes.json` maps attribute fields to discriminative terms
mined offline by scripts/mine_pseudo_attributes.py (seeds + IDF cutoff +
co-occurrence classification). The catalog file itself is NEVER written —
this is a separate in-memory/sidecar artifact (read-only-catalog rule).

Consumed ONLY as clarification entropy/agreement value evidence — pseudo-
attributes are never a hard filter and never a ranking demotion.

Performance: term token-sets are compiled once per lexicon load, and each
row's text tokens are memoized by asin (the catalog is frozen for the
process lifetime) — value evidence for a 1500-row plausible set costs
microseconds per row instead of a full re-tokenization per (field, row).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from neeshops.config.settings import get_settings
from neeshops.retrieval.token_index import index_tokenize
from neeshops.utils.tokens import tokenize

DEFAULT_SIDECAR = Path("data/pseudo_attributes.json")

_ROW_TOKEN_CACHE: dict[str, frozenset[str]] = {}
_ROW_TOKEN_CACHE_LIMIT = 60000


@lru_cache(maxsize=8)
def _compiled_terms(lexicons_key: int, terms: tuple[str, ...]) -> tuple[frozenset[str], ...]:
    del lexicons_key
    return tuple(frozenset(index_tokenize(term)) for term in terms)


_DEFAULT_LEXICONS: Optional[dict[str, list[str]]] = None


def load_pseudo_attributes(path: Optional[Path] = None) -> dict[str, list[str]]:
    """Load (and memoize) the sidecar — one read per process for the
    default path; explicit paths are read fresh (tests may rewrite them)."""
    global _DEFAULT_LEXICONS
    if path is None:
        if _DEFAULT_LEXICONS is not None:
            return _DEFAULT_LEXICONS
        sidecar = get_settings().catalog_path.parent / "pseudo_attributes.json"
    else:
        sidecar = path
    try:
        with open(sidecar, encoding="utf-8") as handle:
            data = json.load(handle)
        lexicons = {
            str(k): [str(v) for v in values]
            for k, values in data.items()
            if isinstance(values, list)
        }
    except (OSError, ValueError):
        lexicons = {}
    if path is None:
        _DEFAULT_LEXICONS = lexicons
    return lexicons


def row_value(
    field: str, row: dict[str, Any], lexicons: Optional[dict[str, list[str]]] = None
) -> Optional[str]:
    """The first pseudo-attribute term for `field` present in the row's
    text — value evidence where the curated extractor has no lexicon hit."""
    if not row:
        return None
    lexicons = lexicons if lexicons is not None else load_pseudo_attributes()
    terms = lexicons.get(field)
    if not terms:
        return None
    asin = str(row.get("parent_asin") or "")
    if asin:
        doc_tokens = _ROW_TOKEN_CACHE.get(asin)
        if doc_tokens is None:
            doc_tokens = frozenset(tokenize(_row_text(row)))
            if len(_ROW_TOKEN_CACHE) < _ROW_TOKEN_CACHE_LIMIT:
                _ROW_TOKEN_CACHE[asin] = doc_tokens
    else:
        doc_tokens = frozenset(tokenize(_row_text(row)))
    compiled = _compiled_terms(id(lexicons), tuple(terms))
    for term_tokens, term in zip(compiled, terms):
        if term_tokens and term_tokens <= doc_tokens:
            return term
    return None


def _row_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("title", "features", "details", "description", "categories", "store"):
        value = row.get(field)
        if isinstance(value, dict):
            parts.extend(f"{k} {v}" for k, v in value.items())
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).lower()
