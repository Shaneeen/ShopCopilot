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
