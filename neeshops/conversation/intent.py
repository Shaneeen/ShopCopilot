"""Intent / scenario routing: is this turn Buying or Browsing?

Buying — specific requirements given early ("black running shoes under $80").
Browsing — vague, exploratory ("I want to refresh my wardrobe").

Stage-1: a lightweight heuristic. Kept as its own module (rather than inline
in the agent) so it can be swapped for a classifier later without touching
orchestration.
"""

from __future__ import annotations

from neeshops.utils.tokens import tokenize

BUYING_SIGNALS = {
    "buy",
    "need",
    "want",
    "looking",
    "under",
    "budget",
    "size",
    "gift",
    "for",
    "$",
}
BROWSING_SIGNALS = {
    "browse",
    "browsing",
    "explore",
    "inspire",
    "inspiration",
    "ideas",
    "something",
    "surprise",
    "unexpected",
    "refresh",
    "upgrade",
    "casual",
    "weekend",
    "nice",
    "preference",
}


def detect_route(
    message: str, previous_route: str | None, constraint_count: int
) -> str:
    """Return "buying" or "browsing".

    A route, once set, is sticky unless the new message gives a strong
    signal the other way — this avoids route flip-flopping turn to turn.

    Signal matching runs on the RAW tokens, not `keywords()`: the
    conversational signal words ("looking", "need", "for") are themselves
    stopwords, so stripping them first erased every buying signal from the
    standard opener and mis-routed it as browsing.
    """
    lowered = message.lower()
    if "preference" in lowered or "don't have" in lowered or "dont have" in lowered:
        if constraint_count == 0 and not (
            "$" in message or any(t.isdigit() for t in set(tokenize(message)))
        ):
            return "browsing"
    tokens = set(tokenize(message))
    has_price = "$" in message or any(t.isdigit() for t in tokens)
    buying_score = (
        len(tokens & BUYING_SIGNALS) + (2 if has_price else 0) + constraint_count
    )
    browsing_score = len(tokens & BROWSING_SIGNALS)
    if buying_score == 0 and browsing_score == 0:
        return previous_route or "browsing"
    if buying_score > browsing_score:
        return "buying"
    if buying_score == browsing_score and constraint_count > 0:
        return "buying"
    return "browsing"
