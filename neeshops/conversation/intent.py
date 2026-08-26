"""Intent / scenario routing: is this turn Buying or Browsing?

Buying — specific requirements given early ("black running shoes under $80").
Browsing — vague, exploratory ("I want to refresh my wardrobe").

Stage-1: a lightweight heuristic. Kept as its own module (rather than inline
in the agent) so it can be swapped for a classifier later without touching
orchestration.
"""
from __future__ import annotations

from neeshops.utils.tokens import keywords

BUYING_SIGNALS = {
    "buy", "need", "want", "looking", "under", "budget", "size", "gift",
    "for", "$",
}
BROWSING_SIGNALS = {
    "browse", "browsing", "explore", "inspire", "ideas", "something",
    "surprise", "unexpected", "refresh", "upgrade",
}


def detect_route(message: str, previous_route: str | None, constraint_count: int) -> str:
    """Return "buying" or "browsing".

    A route, once set, is sticky unless the new message gives a strong
    signal the other way — this avoids route flip-flopping turn to turn.
    """
    tokens = set(keywords(message))
    has_price = "$" in message or any(t.isdigit() for t in tokens)
    buying_score = len(tokens & BUYING_SIGNALS) + (2 if has_price else 0) + constraint_count
    browsing_score = len(tokens & BROWSING_SIGNALS)

    if buying_score == 0 and browsing_score == 0:
        return previous_route or "browsing"
    if buying_score >= browsing_score:
        return "buying"
    return "browsing"
