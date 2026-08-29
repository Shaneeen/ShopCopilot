"""Constraint extraction: turn free text into structured `{field: value}`
updates that `StateManager.apply_turn` can override the previous state with.

Stage-1 implementation is a small rule/keyword-based extractor — enough to
demonstrate the intent-override and no-preference contracts and to unblock
retrieval. Workstream 1 is expected to replace/extend this (regex → NER →
LLM-assisted extraction) without touching its call site in `neeshops/agent.py`.
"""
from __future__ import annotations

import re

from neeshops.models.session import CONSTRAINT_FIELDS, NO_PREFERENCE
from neeshops.utils.tokens import tokenize

_NO_PREFERENCE_PATTERNS = [
    "no preference", "don't care", "doesn't matter", "any is fine",
    "anything is fine", "not picky", "no particular", "either is fine",
]

_COLOR_WORDS = {
    "black", "white", "red", "blue", "green", "yellow", "pink", "purple",
    "brown", "grey", "gray", "beige", "navy", "orange", "cream", "tan",
    "gold", "silver", "wine", "burgundy",
}

_PRICE_RE = re.compile(r"\$?\s?(\d+(?:\.\d+)?)\s*(?:dollars)?")
_UNDER_RE = re.compile(r"under|below|less than|cheaper than|max(?:imum)?")


def extract_constraints(message: str, known_fields: list[str] | None = None) -> dict:
    """Best-effort extraction of constraint updates from one user message.

    Returns only the fields this message actually speaks to — callers apply
    it with override semantics, so omitted fields are left untouched.
    """
    text = message.lower()
    fields = known_fields or CONSTRAINT_FIELDS
    out: dict = {}

    # No-preference detection, e.g. "no preference on color" / "any color is fine"
    for phrase in _NO_PREFERENCE_PATTERNS:
        if phrase in text:
            for field in fields:
                if field in text:
                    out[field] = NO_PREFERENCE

    # Budget: "under $120", "below 80 dollars"
    if _UNDER_RE.search(text):
        price_match = _PRICE_RE.search(text)
        if price_match:
            out["budget"] = float(price_match.group(1))

    # Color: vocabulary match with negation/override awareness (e.g. "forget blue, I want red")
    negated_words = set(
        re.findall(r"(?:forget|not|no|instead of|rather than|drop)\s+([a-z]+)", text)
    )
    tokens_list = tokenize(text)
    candidate_colors = [
        t for t in tokens_list if t in _COLOR_WORDS and t not in negated_words
    ]
    if candidate_colors and "color" not in out:
        out["color"] = candidate_colors[-1]
    elif "color" not in out:
        all_colors = [t for t in tokens_list if t in _COLOR_WORDS]
        if all_colors:
            out["color"] = all_colors[-1]

    return out



def override_intent(previous: dict, updates: dict) -> dict:
    """Pure helper mirroring StateManager's override semantics, exposed for
    unit testing / reuse without needing a live session.

    `updates` always wins over `previous` on shared keys.
    """
    merged = dict(previous)
    merged.update(updates)
    return merged
