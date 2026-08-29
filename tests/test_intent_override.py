"""Intent override: a new explicit value replaces the old one — it never
accumulates. And NO_PREFERENCE fields are never asked about again."""
from neeshops.conversation.constraints import extract_constraints, override_intent
from neeshops.conversation.state import StateManager
from neeshops.models.session import NO_PREFERENCE


def test_override_replaces_not_merges():
    previous = {"color": "blue"}
    updates = {"color": "black"}
    merged = override_intent(previous, updates)
    assert merged["color"] == "black"
    assert merged["color"] != "blue + black"


def test_state_manager_applies_override_semantics():
    sm = StateManager()
    sm.reset("s1", {})
    sm.apply_turn("s1", turn=1, user_message="blue shoes", extracted_constraints={"color": "blue"}, route="buying")
    state = sm.apply_turn(
        "s1", turn=2, user_message="actually I want black", extracted_constraints={"color": "black"}, route="buying"
    )
    assert state.constraint_value("color") == "black"


def test_no_preference_is_recorded_and_not_reasked():
    sm = StateManager()
    sm.reset("s1", {})
    sm.mark_no_preference("s1", "color")
    state = sm.get("s1")
    assert state.has_no_preference("color")

    from neeshops.conversation.clarification import ClarificationEngine

    engine = ClarificationEngine()
    # Even with an empty/broad candidate pool, "color" must never be the
    # attribute asked about again once marked NO_PREFERENCE.
    decision = engine.decide(state, candidates=[], turn=2)
    assert decision["ask_attribute"] != "color"


def test_extract_constraints_detects_no_preference_phrase():
    updates = extract_constraints("I have no preference on color")
    assert updates.get("color") == NO_PREFERENCE

def test_override_material():
    previous = {"material": "leather"}
    updates = {"material": "cotton"}

    merged = override_intent(previous, updates)

    assert merged["material"] == "cotton"
    assert merged["material"] != "leather + cotton"


def test_override_brand():
    previous = {"brand": "nike"}
    updates = {"brand": "adidas"}

    merged = override_intent(previous, updates)

    assert merged["brand"] == "adidas"
    assert merged["brand"] != "nike + adidas"


def test_override_budget():
    previous = {"budget": 120.0}
    updates = {"budget": 80.0}

    merged = override_intent(previous, updates)

    assert merged["budget"] == 80.0
    assert merged["budget"] != 120.0

def test_multiple_overrides_preserve_unrelated_constraints():
    sm = StateManager()
    sm.reset("s1", {})

    sm.apply_turn(
        "s1",
        turn=1,
        user_message="I want blue leather Nike shoes under $120",
        extracted_constraints={
            "color": "blue",
            "material": "leather",
            "brand": "nike",
            "budget": 120.0,
        },
        route="buying",
    )

    state = sm.apply_turn(
        "s1",
        turn=2,
        user_message="Actually, make that black Adidas shoes under $80",
        extracted_constraints={
            "color": "black",
            "brand": "adidas",
            "budget": 80.0,
        },
        route="buying",
    )

    assert state.constraint_value("color") == "black"
    assert state.constraint_value("brand") == "adidas"
    assert state.constraint_value("budget") == 80.0

    # Material wasn't changed, so it should remain.
    assert state.constraint_value("material") == "leather"
