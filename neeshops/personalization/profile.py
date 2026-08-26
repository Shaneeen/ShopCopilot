"""Turn the organiser's anonymised user profile into a *soft* ranking
signal — never a hard filter. An explicit in-conversation request always
takes precedence; this module only nudges ordering among candidates that
already satisfy the stated constraints.
"""
from __future__ import annotations

from typing import Any

from neeshops.models.session import UserProfile
from neeshops.utils.tokens import tokenize


def personalization_boost(product_row: dict[str, Any], profile: UserProfile) -> float:
    """Return a boost in [0, 1] based on overlap between the profile's
    `preference_tags` (e.g. "comfort", "durability", "fit") and the
    product's text fields.

    Stage-1: simple tag/keyword overlap. A workstream can replace this with
    a learned signal without changing the call site in ranking/heuristic.py.
    """
    if not profile.preference_tags:
        return 0.0

    haystack = " ".join(
        str(product_row.get(f, "")) for f in ("title", "description", "categories", "features")
    )
    haystack_tokens = set(tokenize(haystack))
    tags = {t.lower() for t in profile.preference_tags}

    if not haystack_tokens:
        return 0.0

    overlap = len(tags & haystack_tokens)
    return min(overlap / max(len(tags), 1), 1.0)
