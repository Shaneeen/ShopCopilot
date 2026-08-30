"""Wildcard ("other") answers parse into multiple constraints per turn, and
intent-override messages parse their new requirement."""
from neeshops.conversation.constraints import (
    extract_constraints,
    is_intent_override,
)
from neeshops.models.session import NO_PREFERENCE


def test_wildcard_reply_parses_material_and_color():
    updates = extract_constraints(
        "For that, what matters is: cotton; color: black.", slot="other"
    )
    assert updates["material"] == "cotton"
    assert updates["color"] == "black"


def test_wildcard_reply_parses_budget_fragment():
    updates = extract_constraints(
        "For that, what matters is: stainless steel; budget around $27.99.",
        slot="other",
    )
    assert updates["material"] == "stainless steel"
    assert updates["budget"] == 27.99


def test_wildcard_reply_parses_feature_fragment():
    updates = extract_constraints(
        "For that, what matters is: machine washable.", slot="other"
    )
    assert updates["feature"] == "machine washable"


def test_wildcard_no_preference_reply_marks_other():
    updates = extract_constraints(
        "I don't have an additional preference for other.", slot="other"
    )
    assert updates["other"] == NO_PREFERENCE


def test_specific_slot_filling_unchanged():
    updates = extract_constraints("For that, what matters is: cotton.", slot="material")
    assert updates["material"] == "cotton"
    assert "other" not in updates


def test_detects_intent_override_message():
    assert is_intent_override(
        "Actually, ignore my earlier preference. What I need is: stainless steel."
    )
    assert not is_intent_override("I love this preference, keep it.")


def test_override_message_parses_new_requirement():
    updates = extract_constraints(
        "Actually, ignore my earlier preference. What I need is: color: blue."
    )
    assert updates["color"] == "blue"
