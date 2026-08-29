"""Small text-normalisation and query-building helpers.

Re-exports from `neeshops.utils.tokenization` for backwards compatibility.
"""
from __future__ import annotations

from neeshops.utils.tokenization import (
    STOPWORDS,
    build_query,
    build_retrieval_query,
    keywords,
    tokenize,
)

__all__ = [
    "STOPWORDS",
    "tokenize",
    "keywords",
    "build_query",
    "build_retrieval_query",
]

