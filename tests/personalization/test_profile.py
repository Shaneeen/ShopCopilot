from copy import deepcopy

import pytest

from neeshops.models.session import UserProfile
from neeshops.personalization.profile import explain_personalization, personalization_boost


def score(product, tags):
    return personalization_boost(product, UserProfile(preference_tags=tags))


def test_empty_and_missing_profiles_are_safe():
    assert score({"title": "Comfort shoe"}, []) == 0.0
    assert personalization_boost({"title": "Comfort shoe"}, {}) == 0.0


def test_missing_product_fields_are_safe_and_bounded():
    value = score({}, ["comfort"])
    assert value == 0.0
    assert 0.0 <= value <= 1.0


def test_unknown_tag_uses_direct_fallback_only():
    assert score({"title": "Gorpcore hiking jacket"}, ["gorpcore"]) > 0.0
    assert score({"title": "Ordinary hiking jacket"}, ["gorpcore"]) == 0.0


def test_repeated_text_and_duplicate_tags_cannot_game_score():
    once = score({"title": "comfortable shoe"}, ["comfort"])
    spam = score({"title": "comfortable comfortable comfortable shoe"}, ["comfort"])
    duplicates = score({"title": "comfortable shoe"}, ["comfort", "comfort", "comfort"])
    assert spam == once
    assert duplicates == once


def test_title_match_is_stronger_than_description_match():
    title = score({"title": "Cushioned shoe"}, ["comfort"])
    description = score({"description": "x " * 1000 + "cushioned"}, ["comfort"])
    assert title > description > 0.0


def test_profile_confidence_gates_sparse_profiles():
    product = {"title": "comfortable durable stylish warm jacket"}
    sparse = score(product, ["comfort"])
    rich = score(product, ["comfort", "durability", "style", "warmth"])
    assert rich > sparse
    assert explain_personalization(product, {"preference_tags": ["comfort"]})["confidence"] == 0.35


def test_weak_profile_statistics_do_not_change_product_score():
    product = {"title": "comfortable shoe"}
    basic = {"preference_tags": ["comfort"]}
    noisy = {**basic, "rating_style": "harsh", "purchase_frequency": "daily", "average_prior_rating": 1.0}
    assert personalization_boost(product, basic) == personalization_boost(product, noisy)


def test_explanation_and_score_share_one_path():
    product = {"title": "Supportive running shoe", "features": ["breathable mesh"]}
    profile = {"preference_tags": ["comfort", "performance"]}
    explanation = explain_personalization(product, profile)
    assert explanation["score"] == personalization_boost(product, profile)
    assert explanation["matched_tags"] == ["comfort", "performance"]
    assert explanation["field_matches"]["title"]


def test_deterministic_bounded_and_side_effect_free():
    product = {"title": "Thermal fleece", "categories": ["Coats"]}
    profile = {"preference_tags": ["warmth"]}
    before_product, before_profile = deepcopy(product), deepcopy(profile)
    values = [personalization_boost(product, profile) for _ in range(10)]
    assert len(set(values)) == 1
    assert 0.0 <= values[0] <= 1.0
    assert product == before_product and profile == before_profile


@pytest.mark.parametrize("profile", [None, object(), {"preference_tags": None}])
def test_unusual_missing_profile_shapes_do_not_crash(profile):
    assert personalization_boost({"title": "shoe"}, profile) == 0.0
