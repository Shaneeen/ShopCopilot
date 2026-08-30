from copy import deepcopy

import pytest

from neeshops.config.settings import load_strategy
from scripts.evaluate_ranking_ab import strategy_with_personalization
from scripts.interactive_demo import normalize_demo_profile


def test_evaluation_updates_active_weight_without_mutating_defaults():
    original = load_strategy()
    configured = strategy_with_personalization(original, 0.07, 25)

    assert configured["ranking"]["personalization_weight"] == 0.07
    assert configured["ranking"]["deterministic"]["weights"]["personalization"] == 0.07
    assert configured["ranking"]["deterministic"]["rerank_limit"] == 25
    assert configured["ranking"]["deterministic"]["features_enabled"]["personalization"]
    assert original == load_strategy()


def test_zero_weight_disables_only_personalization():
    strategy = deepcopy(load_strategy())
    configured = strategy_with_personalization(strategy, 0.0, 40)

    flags = configured["ranking"]["deterministic"]["features_enabled"]
    assert flags["personalization"] is False
    assert flags["retrieval"] is True
    assert flags["inferred"] is True


def test_negative_weight_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        strategy_with_personalization(load_strategy(), -0.01, 40)


def test_demo_profile_normalizes_tags_and_ignores_unknown_fields():
    assert normalize_demo_profile(
        {"preference_tags": [" comfort ", "durability", "comfort"], "unknown": "x"}
    ) == {"preference_tags": ["comfort", "durability"]}


def test_demo_profile_rejects_non_string_tags():
    with pytest.raises(ValueError, match="list of strings"):
        normalize_demo_profile({"preference_tags": ["comfort", 3]})
