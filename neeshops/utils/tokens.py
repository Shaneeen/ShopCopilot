"""Small text-normalisation helpers shared by retrieval and intent modules.

Deliberately dependency-free (no nltk/spacy) so the baseline has zero heavy
dependencies. A workstream is free to swap this out behind the same
function signatures if a smarter tokenizer is needed later.
"""
from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
    "in", "into", "is", "it", "no", "not", "of", "on", "or", "such",
    "that", "the", "their", "then", "there", "these", "they", "this",
    "to", "was", "will", "with", "i", "me", "my", "want", "need", "looking",
}


def tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    return _TOKEN_RE.findall(text.lower())


def keywords(text: str) -> list[str]:
    """Tokenize and drop stopwords — used to build a BM25 query from a
    free-text user message."""
    return [t for t in tokenize(text) if t not in STOPWORDS]
