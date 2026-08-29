"""Tests for text tokenization, keyword extraction, and multi-turn query representation."""
from neeshops.models.session import NO_PREFERENCE, ConversationState, Turn
from neeshops.utils.tokenization import (
    build_query,
    build_retrieval_query,
    keywords,
    tokenize,
)


def test_tokenize_basic():
    assert tokenize("Black running shoes, model 2026!") == ["black", "running", "shoes", "model", "2026"]
    assert tokenize("") == []
    assert tokenize("   ") == []


def test_keywords_drops_stopwords():
    tokens = keywords("I want to find a comfortable sneaker with mesh")
    assert "i" not in tokens
    assert "want" not in tokens
    assert "to" not in tokens
    assert "a" not in tokens
    assert "comfortable" in tokens
    assert "sneaker" in tokens
    assert "mesh" in tokens


def test_build_query_newest_message_only():
    query = build_retrieval_query("comfortable leather boots")
    assert query == "comfortable leather boots"


def test_build_query_with_active_constraints():
    state = ConversationState(
        session_id="s1",
        constraints={
            "category": "running shoes",
            "color": "black",
            "material": "mesh",
            "budget": 80.0,
            "style": NO_PREFERENCE,
        },
    )
    # Message provides new context; active constraints provide authoritative context
    query = build_retrieval_query("under $80 please", state=state)
    words = query.split()

    assert "80" in words
    assert "running" in words
    assert "shoes" in words
    assert "black" in words
    assert "mesh" in words
    # NO_PREFERENCE must never appear in query
    assert "no_preference" not in words
    assert "NO_PREFERENCE" not in query


def test_build_query_with_multi_turn_history():
    state = ConversationState(
        session_id="s2",
        constraints={"color": "white", "category": "sneakers"},
        history=[
            Turn(turn=1, user_message="I am looking for lightweight sneakers"),
            Turn(turn=2, user_message="white color please"),
        ],
    )
    # Turn 3 message
    query = build_retrieval_query("size 10 for daily walking", state=state)
    words = query.split()

    # Newest message keywords
    assert "size" in words
    assert "10" in words
    assert "daily" in words
    assert "walking" in words

    # Active constraints
    assert "white" in words
    assert "sneakers" in words

    # History keywords
    assert "lightweight" in words


def test_build_query_preserves_order_and_deduplicates():
    state = ConversationState(
        session_id="s3",
        constraints={"category": "sneakers", "color": "black"},
        history=[
            Turn(turn=1, user_message="black sneakers"),
        ],
    )
    query = build_retrieval_query("black running sneakers", state=state)
    # Deduplicated: "black", "running", "sneakers"
    words = query.split()
    assert words == ["black", "running", "sneakers"]
    assert len(words) == len(set(words))
