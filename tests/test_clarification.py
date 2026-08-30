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
def test_answered_question_is_not_repeated():
    sm = StateManager()
    sm.reset("s1", {})

    # Turn 1: system asked for size.
    sm.apply_turn(
        "s1",
        turn=1,
        user_message="I want some shoes",
        extracted_constraints={},
        route="buying",
        asked_attribute="size",
    )

    # Turn 2: user answers the question.
    state = sm.apply_turn(
        "s1",
        turn=2,
        user_message="I'm a size 9",
        extracted_constraints={"size": "9"},
        route="buying",
    )

    engine = ClarificationEngine()
    decision = engine.decide(state, candidates=[], turn=3)

    assert state.constraint_value("size") == "9"
    assert decision["ask_attribute"] != "size"

def test_stops_asking_after_question_budget():
    sm = StateManager()
    sm.reset("s1", {})

    # Simulate two questions already being asked.
    state = sm.apply_turn(
        "s1",
        turn=1,
        user_message="I want shoes",
        extracted_constraints={},
        route="buying",
        asked_attribute="size",
    )

    state = sm.apply_turn(
        "s1",
        turn=2,
        user_message="I'm not sure",
        extracted_constraints={},
        route="buying",
        asked_attribute="color",
    )

    engine = ClarificationEngine()

    # There are candidates, but the 2-question budget is exhausted.
    candidates = ["item1", "item2"]

    decision = engine.decide(state, candidates=candidates, turn=3)

    assert decision["ask_attribute"] is None
    assert decision["question"] is None
    assert decision["should_recommend"] is True