"""Text normalization, tokenization, and multi-turn query representation.

Shared across retrieval, conversation state, intent, and ranking modules.
Dependency-free (no nltk/spacy) to keep the core lightweight and portable.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Sequence

from neeshops.models.session import NO_PREFERENCE, ConversationState

_TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
    "in", "into", "is", "it", "no", "not", "of", "on", "or", "such",
    "that", "the", "their", "then", "there", "these", "they", "this",
    "to", "was", "will", "with", "i", "me", "my", "want", "need", "looking",
    "please", "find", "show", "give", "would", "like", "actually",
}


def tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on alphanumeric characters."""
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def keywords(text: str) -> list[str]:
    """Tokenize and drop stopwords — used for extracting keyword search terms."""
    return [t for t in tokenize(text) if t not in STOPWORDS]


def build_retrieval_query(
    newest_message: str,
    state: Optional[ConversationState] = None,
    max_history_turns: int = 3,
) -> str:
    """Build an enriched multi-turn retrieval query from:
    1. Newest message keywords (highest priority)
    2. Active constraints in ConversationState (authoritative intent-overridden slots)
    3. Conversation history (prior turn utterances for continuous context)

    Deduplicates tokens while preserving logical priority.
    """
    query_tokens: list[str] = []
    seen: set[str] = set()

    def add_token(t: str) -> None:
        if t not in seen and t not in STOPWORDS:
            seen.add(t)
            query_tokens.append(t)

    # 1. Newest message keywords (current user intent)
    for token in keywords(newest_message):
        add_token(token)

    if state:
        # 2. Active constraints (authoritative context)
        # Add textual constraint values (category, color, material, style, brand, use_case, feature)
        for field, value in state.constraints.items():
            if value == NO_PREFERENCE or value is None:
                continue
            if isinstance(value, str):
                for token in keywords(value):
                    add_token(token)
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    if isinstance(item, str):
                        for token in keywords(item):
                            add_token(token)

        # 3. History keywords from previous turns (up to max_history_turns)
        if state.history:
            recent_turns = state.history[-max_history_turns:]
            for past_turn in reversed(recent_turns):
                # Don't duplicate if message is identical to newest_message
                if past_turn.user_message.strip().lower() == newest_message.strip().lower():
                    continue
                for token in keywords(past_turn.user_message):
                    add_token(token)

    return " ".join(query_tokens)


# Convenient alias
build_query = build_retrieval_query
