"""Product model.

Mirrors the official catalog schema (`data/catalog.jsonl`, 50k items from
`Clothing_Shoes_and_Jewelry` — see docs/DATA_ATTRIBUTION.md and the
organiser's `evaluator/local_evaluator.py::searchable_text`/`intent_card`
for the authoritative field list): `parent_asin`, `title`, `categories`
(list), `features` (list), `details` (dict), `store`, `description`,
`price`, `average_rating`, `rating_number`. Kept permissive (`extra`
fields tolerated) since the organiser owns this schema, not us.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class Product(BaseModel):
    model_config = ConfigDict(extra="allow")

    parent_asin: str
    title: str
    categories: list[str] = []
    features: list[str] = []
    details: dict[str, Any] = {}
    store: Optional[str] = None
    description: Optional[Any] = None
    price: Optional[float] = None
    average_rating: Optional[float] = None
    rating_number: Optional[int] = None

    @classmethod
    def from_catalog_row(cls, row: dict[str, Any]) -> "Product":
        """Build a Product from one raw catalog.jsonl record. Left liberal
        on purpose — the organiser's schema is authoritative; this just
        normalises the handful of fields NeeShops actively reads."""
        return cls(**row)
