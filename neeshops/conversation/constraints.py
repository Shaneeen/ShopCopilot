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
    "anything is fine", "not picky", "no particular", "either is fine","don't mind"
]
_NO_PREFERENCE_FIELD_RE = re.compile(
    r"\b(?:any|whatever)\s+"
    r"(category|material|color|size|style|brand|budget|feature|use[_ ]?case)"
    r"\s+(?:is|are)\s+fine\b",
    re.IGNORECASE,
)

_COLOR_WORDS = {
    "black", "white", "red", "blue", "green", "yellow", "pink", "purple",
    "brown", "grey", "gray", "beige", "navy", "orange", "cream", "tan",
    "gold", "silver", "wine", "burgundy",
}

_CATEGORY_WORDS = {
    "shoes",
    "shirts",
    "pants",
    "dresses",
    "jackets",
    "bags",
    "watches",
    "headphones",
}
_MATERIAL_WORDS = {
    "leather",
    "cotton",
    "wool",
    "linen",
    "silk",
    "denim",
    "nylon",
    "polyester",
    "suede",
}
_STYLE_WORDS = {
    "casual",
    "formal",
    "sporty",
    "elegant",
    "vintage",
    "classic",
    "modern",
    "minimalist",
}
_BRAND_WORDS = {
    "nike",
    "adidas",
    "puma",
    "reebok",
    "asics",
    "converse",
    "vans",
}
_FEATURE_WORDS = {
    "waterproof",
    "breathable",
    "lightweight",
    "comfortable",
    "durable",
    "reversible",
    "insulated",
    "adjustable",
}
_USE_CASE_WORDS = {
    "running",
    "work",
    "office",
    "wedding",
    "travel",
    "gym",
    "party",
    "hiking",
    "school",
    "everyday",
    "casual",
}
_PRICE_RE = re.compile(r"\$?\s?(\d+(?:\.\d+)?)\s*(?:dollars)?")
_BUDGET_RE = re.compile(
    r"under|below|less than|cheaper than|max(?:imum)?|"
    r"up to|budget|spend|no more than",
    re.IGNORECASE,
)
_SIZE_RE = re.compile(r"\bsize\s*([0-9]+(?:\.[0-9]+)?|[xsml]{1,3})\b", re.IGNORECASE)


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
    # No-preference: "any material is fine", "whatever brand is fine"
    match = _NO_PREFERENCE_FIELD_RE.search(text)
    if match:
        field = match.group(1).replace(" ", "_")
        out[field] = NO_PREFERENCE

    # Budget: "under $120", "below 80 dollars"
    if _BUDGET_RE.search(text):
        price_match = _PRICE_RE.search(text)
        if price_match:
            out["budget"] = float(price_match.group(1))

    # Color: simple vocabulary match
    tokens = set(tokenize(text))
    color_hit = tokens & _COLOR_WORDS
    if color_hit and "color" not in out:
        out["color"] = sorted(color_hit)[0]
    # Category: simple vocabulary match
    category_hit = tokens & _CATEGORY_WORDS
    if category_hit and "category" not in out:
        out["category"] = sorted(category_hit)[0]
    # Material: simple vocabulary match
    material_hit = tokens & _MATERIAL_WORDS
    if material_hit and "material" not in out:
        out["material"] = sorted(material_hit)[0]
    # Style: simple vocabulary match
    style_hit = tokens & _STYLE_WORDS
    if style_hit and "style" not in out:
        out["style"] = sorted(style_hit)[0]
    # Brand: simple vocabulary match
    brand_hit = tokens & _BRAND_WORDS
    if brand_hit and "brand" not in out:
        out["brand"] = sorted(brand_hit)[0]
    feature_hit = tokens & _FEATURE_WORDS
    if feature_hit and "feature" not in out:
        out["feature"] = sorted(feature_hit)[0]
    # Use case: simple vocabulary match
    use_case_hit = tokens & _USE_CASE_WORDS
    if use_case_hit and "use_case" not in out:
        out["use_case"] = sorted(use_case_hit)[0]
    # Size: match explicit "size X" phrases
    size_match = _SIZE_RE.search(text)
    if size_match and "size" not in out:
        out["size"] = size_match.group(1).upper()
    return out


def override_intent(previous: dict, updates: dict) -> dict:
    """Pure helper mirroring StateManager's override semantics, exposed for
    unit testing / reuse without needing a live session.

    `updates` always wins over `previous` on shared keys.
    """
    merged = dict(previous)
    merged.update(updates)
    return merged
