"""Synthetic P2-like ranking data; these are not real retrieval results."""
from __future__ import annotations

from copy import deepcopy

from neeshops.config.settings import load_strategy
from neeshops.models.session import ConversationState, UserProfile
from neeshops.retrieval.base import Candidate


SYNTHETIC_BOOT_CATALOG = {
    "LEATHER_BLACK": {
        "title": "Black genuine leather casual ankle boot",
        "price": 89.99,
        "category": "ankle boots",
        "categories": ["Women", "Shoes", "Ankle Boots"],
        "color": "black",
        "material": "genuine leather",
        "style": "casual",
        "size": "8",
        "brand": "Adidas",
        "features": ["side zipper", "casual everyday comfort"],
    },
    "SYNTHETIC_BLACK": {
        "title": "Black synthetic casual ankle boot",
        "price": 69.99,
        "category": "ankle boots",
        "color": "black",
        "material": "synthetic",
        "style": "casual",
        "size": "8",
        "brand": "Adidas",
        "features": ["side zipper"],
    },
    "LEATHER_BROWN": {
        "title": "Brown genuine leather casual ankle boot",
        "price": 99.00,
        "category": "ankle boots",
        "color": "brown",
        "material": "genuine leather",
        "style": "casual",
        "size": "8",
        "brand": "Adidas",
        "features": ["side zipper"],
    },
    "LEATHER_HIGH": {
        "title": "Black leather knee-high boot",
        "price": 119.00,
        "category": "knee high boots",
        "color": "black",
        "material": "leather",
        "style": "casual",
        "size": "8",
        "brand": "Adidas",
        "features": ["tall shaft"],
    },
    "SNEAKER": {
        "title": "Generic black sneaker",
        "price": 49.00,
        "category": "sneakers",
        "color": "black",
        "material": "canvas",
        "style": "casual",
        "size": "8",
        "brand": "Generic",
        "features": ["lightweight"],
    },
    "SPARSE": {"title": "Mystery ankle boot", "features": []},
}


SYNTHETIC_BOOT_CANDIDATES = [
    Candidate("SYNTHETIC_BLACK", 0.99, "bm25"),
    Candidate("LEATHER_BLACK", 0.82, "bm25+semantic"),
    Candidate("LEATHER_BROWN", 0.78, "semantic"),
    Candidate("LEATHER_HIGH", 0.74, "bm25+semantic"),
    Candidate("SNEAKER", 0.70, "bm25"),
]


def boot_state(**overrides) -> ConversationState:
    constraints = {
        "category": "ankle boots",
        "color": "black",
        "material": "leather",
        "size": "8",
        "budget": 120,
        "style": "casual",
    }
    constraints.update(overrides)
    return ConversationState(session_id="synthetic-rank", constraints=constraints)


def deterministic_strategy(**updates) -> dict:
    strategy = deepcopy(load_strategy())
    strategy["ranking"]["deterministic"].update(updates)
    return strategy


def profile_state(*tags: str, **constraints) -> ConversationState:
    return ConversationState(
        session_id="synthetic-profile",
        constraints=constraints,
        user_profile=UserProfile(preference_tags=list(tags)),
    )
