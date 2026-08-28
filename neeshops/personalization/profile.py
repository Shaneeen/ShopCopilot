"""Cheap, deterministic personalisation signals for valid candidates.

The ranker calls :func:`personalization_boost` after retrieval and explicit
constraint filtering.  This module never changes candidate eligibility.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Mapping

from neeshops.models.session import UserProfile


FIELD_WEIGHTS = {"title": 1.0, "category": 0.6, "description": 0.3}

# Deliberately small: these are the preference concepts present in the dev
# data. Unknown tags fall back to matching their own normalised text.
TAG_EXPANSIONS: dict[str, frozenset[str]] = {
    "comfort": frozenset({"comfort", "comfortable", "cushion", "cushioned", "padded", "soft", "supportive", "ergonomic", "breathable", "memory foam"}),
    "durability": frozenset({"durability", "durable", "reinforced", "rugged", "sturdy", "long lasting", "heavy duty", "resistant"}),
    "fit": frozenset({"fit", "fitted", "adjustable", "stretch", "stretchy", "wide width", "slim fit", "relaxed fit"}),
    "material": frozenset({"material", "fabric", "cotton", "leather", "wool", "polyester", "nylon", "silk", "linen"}),
    "style": frozenset({"style", "stylish", "fashion", "classic", "modern", "casual", "formal"}),
    "performance": frozenset({"performance", "athletic", "running", "training", "sport", "moisture wicking"}),
    "warmth": frozenset({"warmth", "warm", "insulated", "thermal", "fleece", "lined"}),
    "weather": frozenset({"weather", "waterproof", "water resistant", "windproof", "rain", "snow"}),
}


def _value(source: object, name: str, default: object = None) -> object:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


@lru_cache(maxsize=4096)
def _normalise_cached(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _normalise_text(value: object) -> str:
    """Flatten common catalog values into boundary-safe normalised text."""
    if value is None:
        return ""
    if isinstance(value, Mapping):
        value = " ".join(f"{key} {item}" for key, item in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        value = " ".join(str(item) for item in value)
    return _normalise_cached(str(value))


def _extract_profile_tags(profile: object) -> list[str]:
    raw_tags = _value(profile, "preference_tags", []) or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    return sorted({_normalise_text(tag) for tag in raw_tags if _normalise_text(tag)})


def _extract_product_fields(product: object) -> dict[str, str]:
    return {
        "title": _normalise_text(_value(product, "title", "")),
        "category": _normalise_text(_value(product, "categories", _value(product, "category", ""))),
        "description": _normalise_text([
            _value(product, "description", ""),
            _value(product, "features", ""),
            _value(product, "details", ""),
        ]),
    }


def _contains_term(text: str, term: str) -> bool:
    # Normalisation pads neither side, so add spaces to preserve word/phrase
    # boundaries (e.g. "fit" must not match "outfit").
    return bool(text and term and f" {term} " in f" {text} ")


def _match_details(tags: list[str], fields: dict[str, str]) -> tuple[float, list[str], list[str], dict[str, bool]]:
    if not tags:
        return 0.0, [], [], {field: False for field in FIELD_WEIGHTS}
    matched_tags: list[str] = []
    matched_terms: set[str] = set()
    field_matches = {field: False for field in FIELD_WEIGHTS}
    tag_scores: list[float] = []
    max_field_weight = sum(FIELD_WEIGHTS.values())
    for tag in tags:
        terms = TAG_EXPANSIONS.get(tag, frozenset({tag}))
        tag_weight = 0.0
        tag_matched = False
        for field, weight in FIELD_WEIGHTS.items():
            hits = {term for term in terms if _contains_term(fields[field], term)}
            if hits:
                tag_weight += weight  # presence only; repetition cannot help
                tag_matched = True
                field_matches[field] = True
                matched_terms.update(hits)
        if tag_matched:
            matched_tags.append(tag)
        tag_scores.append(tag_weight / max_field_weight)
    return sum(tag_scores) / len(tag_scores), matched_tags, sorted(matched_terms), field_matches


def _profile_confidence(profile: object) -> float:
    count = len(_extract_profile_tags(profile))
    if count == 0:
        return 0.0
    if count == 1:
        return 0.35
    if count <= 3:
        return 0.70
    return 1.0


def explain_personalization(product_row: object, profile: object) -> dict[str, Any]:
    """Return debug metadata computed by the same path as the public score."""
    tags = _extract_profile_tags(profile)
    fields = _extract_product_fields(product_row)
    match_score, matched_tags, matched_terms, field_matches = _match_details(tags, fields)
    confidence = _profile_confidence(profile)
    score = max(0.0, min(1.0, match_score * confidence))
    return {
        "score": score,
        "confidence": confidence,
        "matched_tags": matched_tags,
        "matched_terms": matched_terms,
        "field_matches": field_matches,
    }


def personalization_boost(product_row: dict[str, Any], profile: UserProfile) -> float:
    """Return a deterministic score in ``[0, 1]`` for an already-valid candidate.

    The argument order is the existing 3A integration contract. Inputs are
    read only, missing fields are safe, and no filtering or I/O occurs.
    """
    return float(explain_personalization(product_row, profile)["score"])
