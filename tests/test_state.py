"""Session lifecycle: reset() must precede respond(); state persists across
turns within a session."""
from neeshops.conversation.state import StateManager


def test_reset_creates_session():
    sm = StateManager()
    state = sm.reset("s1", {"preference_tags": ["comfort"]})
    assert state.session_id == "s1"
    assert state.turn == 0
    assert state.user_profile.preference_tags == ["comfort"]


def test_get_before_reset_does_not_crash():
    sm = StateManager()
    # Contract says reset() must happen first, but the manager should fail
    # soft (start a blank session) rather than raise on a missing reset.
    state = sm.get("never-reset")
    assert state.session_id == "never-reset"


def test_constraints_persist_across_turns():
    sm = StateManager()
    sm.reset("s1", {})
    sm.apply_turn("s1", turn=1, user_message="black shoes", extracted_constraints={"color": "black"}, route="buying")
    state = sm.apply_turn("s1", turn=2, user_message="under $100", extracted_constraints={"budget": 100}, route="buying")

    assert state.turn == 2
    assert state.constraint_value("color") == "black"
    assert state.constraint_value("budget") == 100


def test_asked_attributes_tracked():
    sm = StateManager()
    sm.reset("s1", {})
    state = sm.apply_turn(
        "s1", turn=1, user_message="shoes", extracted_constraints={}, route="buying",
        asked_attribute="size",
    )
    assert "size" in state.asked_attributes
