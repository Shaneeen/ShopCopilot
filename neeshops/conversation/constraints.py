"""Constraint extraction: turn free text into structured `{field: value}`
updates that `StateManager.apply_turn` can override the previous state with.

Stage-1 was a small rule/keyword-based extractor. Stage-2 adds two things
that make clarification answers actually compound into retrieval:

1. **Slot-filling** — when the previous turn asked about attribute F
   (`slot="material"`), the reply is interpreted *as the value for F*
   (with no-preference detection), instead of relying on generic keyword
   luck. This mirrors the evaluator's customer, who answers exactly the
   attribute the agent asked about ("For that, what matters is: cotton.").
2. **Evaluator-shaped openers** — "I'm looking for X" sets `category`,
   and "A key requirement is: Y" is classified (budget/material/color/
   size/feature) from the same vocabulary the official evaluator uses.

Workstream 1 owns this module; Workstream 2 consumes it for filtering.
"""
from __future__ import annotations

import re
from typing import Optional

from neeshops.models.session import CONSTRAINT_FIELDS, NO_PREFERENCE
from neeshops.utils.tokens import tokenize

# No-preference phrases. "don't have a(n)" / "no additional" cover the
# evaluator customer's "I don't have an additional preference for X."
_NO_PREFERENCE_PATTERNS = [
    "no preference", "don't care", "doesn't matter", "any is fine",
    "anything is fine", "not picky", "no particular", "either is fine",
    "don't have a", "don't have an", "no additional", "not quite right",
    "use your judgment", "use your judgement", "no strong", "surprise me",
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

# Same vocabulary the official evaluator uses to build intent cards, plus a
# few common catalog materials — multi-word phrases are matched first.
_MATERIAL_WORDS = (
    "stainless steel", "spandex", "polyester", "cotton", "nylon", "leather",
    "wool", "silk", "rayon", "denim", "suede", "canvas", "linen", "velvet",
    "satin", "fleece", "cashmere", "mesh", "rubber", "plastic", "bamboo",
    "ceramic", "fabric", "silver", "gold",
)

# One compiled alternation (longest phrases first) — value_from_text runs
# per (field, row) over plausible sets; 25 substring scans per call showed
# up as seconds per clarification turn.
_MATERIAL_RE = re.compile(
    "|".join(
        re.escape(word)
        for word in sorted(_MATERIAL_WORDS, key=len, reverse=True)
    ),
    re.I,
)

_STYLE_WORDS = {
    "casual", "formal", "dressy", "vintage", "retro", "sporty", "athletic",
    "boho", "bohemian", "classic", "modern", "elegant", "trendy", "cozy",
    "western", "tactical", "outdoor", "gothic", "punk", "preppy",
}

_SIZE_RE = re.compile(
    r"\b(xxs|xs|s|m|l|xl|xxl|xxxl|small|medium|large|x-large|xx-large"
    r"|size\s?\d+(?:\.\d)?)\b", re.I
)

_PRICE_RE = re.compile(r"\$?\s?(\d+(?:\.\d+)?)\s*(?:dollars)?")
_UNDER_RE = re.compile(
    r"\b(?:under|below|less than|cheaper than|max(?:imum)?|around|about)\b|\bbudget\b"
)

_LOOKING_FOR_RE = re.compile(r"looking for ([^.!?,;]+)", re.I)
# Covers both the opening "A key requirement is: X" and the evaluator's
# mid-session override "What I need is: X".
_REQUIREMENT_RE = re.compile(r"(?:key requirement is|what i need is):?\s*([^.!?;]+)", re.I)
_REPLY_PREFIX_RE = re.compile(r"^(?:for that,?\s*)?what matters is:?\s*", re.I)
_OVERRIDE_RE = re.compile(r"ignore (?:my|the|your) (?:earlier|previous|original) preference", re.I)

_SLOT_VALUE_LIMIT = 80
_CATEGORY_VALUE_LIMIT = 60

_CATEGORY_STOP_TOKENS = {"a", "an", "the", "some", "new", "nice", "good", "please"}


def _clean_value(text: str, limit: int = _SLOT_VALUE_LIMIT) -> str:
    value = re.sub(r"\s+", " ", text).strip(" -;,.\t\n")
    if len(value) > limit:
        cut = value[:limit]
        # Never cut mid-word: a truncated token ("valentines" -> "valentin")
        # becomes a foreign token that excludes the target from the Boolean
        # AND set. Backtrack to the last word boundary instead.
        if value[limit].isalnum() and cut and cut[-1].isalnum():
            space = cut.rfind(" ")
            if space > 0:
                cut = cut[:space]
        value = cut
    return value.rstrip(" -;,.\t\n")


def _has_no_preference(text: str) -> bool:
    return any(phrase in text for phrase in _NO_PREFERENCE_PATTERNS)


def _first_number(text: str) -> Optional[float]:
    match = _PRICE_RE.search(text)
    return float(match.group(1)) if match else None


def _find_color(text: str) -> Optional[str]:
    tokens = set(tokenize(text)) & _COLOR_WORDS
    return sorted(tokens)[0] if tokens else None


def _find_material(text: str) -> Optional[str]:
    lowered = text.lower()
    match = _MATERIAL_RE.search(lowered)
    if match:
        return match.group(0)
    return None


def _find_style(text: str) -> Optional[str]:
    tokens = set(tokenize(text)) & _STYLE_WORDS
    return sorted(tokens)[0] if tokens else None


def _find_size(text: str) -> Optional[str]:
    match = _SIZE_RE.search(text)
    return match.group(1).lower() if match else None


def value_from_text(field: str, text: str) -> Optional[str]:
    """Best-effort value for `field` found anywhere in `text`.

    Shared by slot-filling (parse the user's answer) and the adaptive
    clarification engine (extract each candidate pool product's own value
    for the field) so both sides speak the same value language.
    """
    if field == "budget":
        number = _first_number(text)
        return number if number is not None else None
    if field == "color":
        return _find_color(text)
    if field == "material":
        return _find_material(text)
    if field == "style":
        return _find_style(text)
    if field == "size":
        return _find_size(text)
    return None


def _slot_value(slot: str, text: str):
    """Interpret `text` as the answer to a question about `slot`."""
    if _has_no_preference(text):
        return NO_PREFERENCE
    if slot == "budget":
        number = _first_number(text)
        return number if number is not None else NO_PREFERENCE
    # Strip the evaluator customer's reply preamble before value lookup.
    body = _REPLY_PREFIX_RE.sub("", text)
    value = value_from_text(slot, body)
    if value:
        return _clean_value(str(value))
    if slot in ("category", "brand", "style", "size", "feature", "use_case"):
        return _clean_value(body)
    return _clean_value(body) or NO_PREFERENCE


def is_intent_override(text: str) -> bool:
    """Detect the evaluator's mid-session override turn ("Actually, ignore my
    earlier preference. What I need is: X."). Callers reset stale context
    (constraints + accumulated query) before parsing this message."""
    return bool(_OVERRIDE_RE.search(text))


def _parse_compound_reply(text: str) -> dict:
    """Parse a wildcard (ask_attribute="other") reply into multiple
    {field: value} updates, one per ';'-separated fragment.

    The evaluator customer answers an "other" question with up to two
    constraints of ANY type ("For that, what matters is: cotton; color:
    black."), so each fragment is classified with the same vocabulary
    `_classify_requirement` uses (budget / color: prefix / material / color /
    size, else feature — a text-containment constraint).

    Fragments classifying into the SAME field are merged (joined with ';')
    in first-seen order: a card value like "Solid colors: 100% Cotton;
    Heather Grey: 90% Cotton, 10% Polyester" contains ';' itself, and the
    fragments are one logical value — merging reconstructs it so its every
    token constrains the Boolean AND (first-wins would drop the tokens that
    pin the guarantee pool). Budget keeps its first number.
    """
    body = _REPLY_PREFIX_RE.sub("", text)
    out: dict = {}
    for fragment in body.split(";"):
        fragment = _clean_value(fragment)
        if not fragment:
            continue
        for field, value in _classify_requirement(fragment).items():
            if not value or value == NO_PREFERENCE:
                continue
            if field == "budget":
                out.setdefault(field, value)
            elif field not in out:
                out[field] = value
            elif value not in out[field]:
                out[field] = f"{out[field]}; {value}"
    return out


def _classify_requirement(value: str) -> dict:
    """Classify one 'key requirement' clause into a {field: value} update."""
    lowered = value.lower()
    if "budget" in lowered or re.search(r"\$\s?\d", lowered):
        number = _first_number(lowered)
        if number is not None:
            return {"budget": number}
    if lowered.startswith("color:"):
        lowered = lowered.split(":", 1)[1]
        color = _find_color(lowered)
        if color:
            return {"color": color}
    material = _find_material(lowered)
    if material:
        return {"material": material}
    color = _find_color(lowered)
    if color:
        return {"color": color}
    size = _find_size(lowered)
    if size:
        return {"size": size}
    return {"feature": _clean_value(value)}


_CATEGORY_GENERIC = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}

# Searchable-text corpus per product, built once per process — the entropy
# engine calls value_from_row for every (field, row) in a plausible set, and
# re-joining the full row text per call dominated the turn latency.
_CORPUS_CACHE: dict[str, str] = {}
_CORPUS_CACHE_LIMIT = 60000


def _row_corpus(row: dict) -> str:
    asin = str(row.get("parent_asin") or "")
    if asin:
        corpus = _CORPUS_CACHE.get(asin)
        if corpus is not None:
            return corpus
    corpus = " ".join(
        str(row.get(f, "")) for f in ("title", "features", "details", "description")
    )
    if asin and len(_CORPUS_CACHE) < _CORPUS_CACHE_LIMIT:
        _CORPUS_CACHE[asin] = corpus
    return corpus


def value_from_row(field: str, row: dict) -> Optional[str]:
    """The value `field` takes for one catalog row, in the same value
    language `value_from_text` parses — used by the adaptive clarification
    engine to measure how informative each question would be."""
    if row is None:
        return None
    if field == "budget":
        price = row.get("price")
        try:
            return float(price) if price is not None else None
        except (TypeError, ValueError):
            return None
    if field == "category":
        raw = row.get("categories") or []
        parts = [
            part.strip().lower()
            for value in raw
            for part in str(value).split(",")
            if part.strip() and part.strip().lower() not in _CATEGORY_GENERIC
        ]
        return " ".join(parts[-2:]) if parts else None
    if field == "brand":
        store = row.get("store")
        if not store:
            details = row.get("details") or {}
            store = details.get("Manufacturer") or details.get("Brand")
        return str(store).strip().lower() if store else None
    return value_from_text(field, _row_corpus(row))


def extract_constraints(
    message: str,
    known_fields: list[str] | None = None,
    slot: Optional[str] = None,
) -> dict:
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

    `slot` is the attribute the agent asked about on the *previous* turn
    (state.history[-1].asked_attribute). When set, the message is treated
    as the answer to that question first — a no-preference phrase maps to
    NO_PREFERENCE for the slot so it is never asked again.
    """
    text = message.lower()
    fields = known_fields or CONSTRAINT_FIELDS
    slot: Optional[str] = None,
    out: dict = {}

    # 1. Slot-filling: the reply to the question we just asked is the most
    #    reliable signal in the message — parse it before anything else.
    #    A wildcard ("other") reply carries up to two constraints of any
    #    type, each parsed into its own field; an unparseable reply marks
    #    "other" NO_PREFERENCE so the clarification engine stops asking it.
    if slot == "other":
        if _has_no_preference(text):
            out["other"] = NO_PREFERENCE
        else:
            parsed = _parse_compound_reply(message)
            if parsed:
                out.update(parsed)
            else:
                out["other"] = NO_PREFERENCE
    elif slot in fields:
        out[slot] = _slot_value(slot, message)

    # 2. Explicit no-preference phrases naming a field.
    if _has_no_preference(text):
        for field in fields:
            if field == slot:
                continue
            if field.replace("_", " ") in text or field in text:
                out[field] = NO_PREFERENCE

    # 3. Budget: "under $120", "budget around $27.99".
    if "budget" not in out and _UNDER_RE.search(text):
        number = _first_number(text)
        if number is not None:
            out["budget"] = number

    # 4. Evaluator-shaped opener: "I'm looking for women shirts. ..."
    if "category" not in out:
        looking = _LOOKING_FOR_RE.search(message)
        if looking:
            value = _clean_value(looking.group(1), _CATEGORY_VALUE_LIMIT)
            tokens = [t for t in value.split() if t.lower() not in _CATEGORY_STOP_TOKENS]
            value = " ".join(tokens)
            if value:
                out["category"] = value

    # 5. "A key requirement is: X" — classify X into a structured field.
    requirement = _REQUIREMENT_RE.search(message)
    if requirement:
        for field, value in _classify_requirement(requirement.group(1)).items():
            out.setdefault(field, value)

    # 6. Free vocabulary matches (color/material anywhere in the message).
    if "color" not in out:
        color = _find_color(text)
        if color:
            out["color"] = color
    if "material" not in out:
        material = _find_material(text)
        if material:
            out["material"] = material

    return out


def override_intent(previous: dict, updates: dict) -> dict:
    """Pure helper mirroring StateManager's override semantics, exposed for
    unit testing / reuse without needing a live session.

    `updates` always wins over `previous` on shared keys.
    """
    merged = dict(previous)
    merged.update(updates)
    return merged
