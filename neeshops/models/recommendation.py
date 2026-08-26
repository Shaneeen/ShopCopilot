"""Recommendation model — what the ranking stage hands back to the agent."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Recommendation(BaseModel):
    parent_asin: str
    score: float
    reason: Optional[str] = None
    """Human-readable justification (e.g. "best value", "closest to your
    style"). Never a fabricated numeric confidence — see docs/neeshops/COMPETITION_NOTES.md.
    """
    source: Optional[str] = None
    """Which retriever(s) surfaced this candidate, e.g. "bm25", "semantic",
    "bm25+semantic". Useful for debugging and for research-agent analysis."""
