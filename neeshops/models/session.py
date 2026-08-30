"""Session-level data models.

`ConversationState` is the schema for everything we remember about one
conversation. Mutation *logic* (intent override, no-preference handling,
etc.) lives in `neeshops.conversation.state.StateManager` — this module only
defines the shape of the data, so other modules (retrieval, ranking,
research) can depend on it without pulling in conversation logic.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

NO_PREFERENCE = "NO_PREFERENCE"

# The constraint slots the system understands. Kept as a plain list (not an
# Enum) so a workstream can extend it without touching every call site.
CONSTRAINT_FIELDS = [
    "category",
    "material",
    "color",
    "size",
    "style",
    "brand",
    "budget",
    "feature",
    "use_case",
]


class Turn(BaseModel):
    """One exchange, kept for history/debugging and for the research agent."""

    turn: int
    user_message: str
    route: Optional[str] = None  # "buying" | "browsing"
    asked_attribute: Optional[str] = None
    returned_asins: list[str] = Field(default_factory=list)
    informative: bool = False
    """True when the user's message yielded at least one usable constraint
    value (a no-preference reply is not informative). The clarification
    engine uses this to stop asking once replies stop carrying information."""


class InferredSlot(BaseModel):
    """An attribute value inferred from top-10 pool agreement (pillar III:
    Personalized Context Distillation, short-term). Bonus-only in ranking —
    NEVER a filter — and decayed with age so stale inferences fade."""

    value: Any
    weight: float = 1.0
    updated_turn: int = 0


class UserProfile(BaseModel):
    """Organiser-provided anonymised profile. See
    neeshops/personalization/profile.py for how this becomes soft signals —
    nothing here should be treated as a hard constraint.
    """

    purchase_frequency: Optional[str] = None
    average_prior_rating: Optional[float] = None
    rating_style: Optional[str] = None
    preference_tags: list[str] = Field(default_factory=list)
    summary: Optional[str] = None


class ConversationState(BaseModel):
    session_id: str
    turn: int = 0
    route: Optional[str] = None  # "buying" | "browsing"

    constraints: dict[str, Any] = Field(default_factory=dict)
    """e.g. {"color": "black", "budget": 120}. A value of NO_PREFERENCE means
    the user was asked and explicitly doesn't care — never ask again."""

    stale: dict[str, Any] = Field(default_factory=dict)
    """Slots erased by an intent override / route flip (pillar II: Intent
    Override — slot erasure and rewriting). Excluded from filter demotion,
    weighted 0.3 in ranking coverage, recoverable when re-affirmed."""

    inferred: dict[str, InferredSlot] = Field(default_factory=dict)
    """Agreement-inferred attributes: when the top-10 pool agrees on a value
    for an un-asked attribute, it's recorded here as a decaying bonus-only
    signal (never a filter, never overriding explicit constraints)."""

    asked_attributes: list[str] = Field(default_factory=list)
    """Attributes we've already asked about this session (whether or not the
    user answered), so the clarification engine doesn't repeat itself."""

    history: list[Turn] = Field(default_factory=list)
    user_profile: UserProfile = Field(default_factory=UserProfile)
    previous_recommendations: list[str] = Field(default_factory=list)
    """parent_asins already shown, for dedup / "find similar" follow-ups."""

    def constraint_value(self, field: str) -> Optional[Any]:
        return self.constraints.get(field)

    def has_no_preference(self, field: str) -> bool:
        return self.constraints.get(field) == NO_PREFERENCE

    def is_unset(self, field: str) -> bool:
        return field not in self.constraints
