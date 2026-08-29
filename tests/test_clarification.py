from neeshops.conversation.clarification import ClarificationEngine
from neeshops.conversation.state import StateManager
from neeshops.models.session import NO_PREFERENCE


def test_does_not_ask_answered_attribute():
    sm = StateManager()
    sm.reset("s1", {})

    state = sm.apply_turn(
        "s1",
        turn=1,
        user_message="I want black shoes",
        extracted_constraints={"color": "black"},
        route="buying",
    )

    engine = ClarificationEngine()

    decision = engine.decide(state, candidates=[], turn=2)

    assert decision["ask_attribute"] != "color"


def test_does_not_ask_already_asked_attribute():
    sm = StateManager()
    sm.reset("s1", {})

    state = sm.apply_turn(
        "s1",
        turn=1,
        user_message="I want shoes",
        extracted_constraints={},
        route="buying",
        asked_attribute="size",
    )

    engine = ClarificationEngine()

    decision = engine.decide(state, candidates=[], turn=2)

    assert decision["ask_attribute"] != "size"


def test_does_not_ask_no_preference_attribute():
    sm = StateManager()
    sm.reset("s1", {})

    sm.mark_no_preference("s1", "color")
    state = sm.get("s1")

    engine = ClarificationEngine()

    decision = engine.decide(state, candidates=[], turn=2)

    assert decision["ask_attribute"] != "color"
    