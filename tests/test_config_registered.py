"""Config integration: every new v2 strategy key must be (a) present in the
shipped default_strategy.json AND (b) registered in SAFE_PARAMETERS — an
unregistered key is silently dropped by the research agent's parameter
guard and never read by consuming code. This is the #1 integration bug the
implementation spec warns about."""
from __future__ import annotations

import json
from pathlib import Path

from neeshops.config.settings import load_strategy
from neeshops.research.experiment import SAFE_PARAMETERS

STRATEGY_PATH = (
    Path(__file__).resolve().parents[1] / "neeshops" / "config" / "default_strategy.json"
)

# Every dot-path this restructure (docs/IMPLEMENTATION_V2.md) relies on.
V2_KEYS = [
    "retrieval.guarantee.enabled",
    "retrieval.guarantee.slots",
    "retrieval.guarantee.rerank_floor",
    "retrieval.guarantee.plausible_set_limit",
    "retrieval.min_pool_topup",
    "ranking.coverage_weight",
    "ranking.coverage_salience_weight",
    "ranking.full_match_bonus",
    "ranking.browsing_popularity_bump",
    "ranking.deterministic.weights.inferred",
    "ranking.deterministic.features_enabled.inferred",
    "ranking.llm.gate_margin",
    "ranking.llm.gate_twins",
    "ranking.llm.blend_epsilon",
    "clarification.max_questions_per_session",
    "clarification.min_candidates_before_recommend",
    "clarification.other_max_asks",
    "clarification.last_question_turn",
    "clarification.margin_stop",
    "clarification.entropy_top_k",
    "clarification.entropy_plausible_limit",
    "clarification.entropy_row_cap",
    "intent.route_flip_erase_weight",
    "intent.inferred_decay",
    "feature_flags.enable_semantic_retrieval",
    "feature_flags.enable_llm_reranker",
]


def _walk(d, prefix=""):
    for key, value in d.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _walk(value, prefix=path + ".")
        else:
            yield path


def test_shipped_strategy_has_no_unregistered_v2_keys():
    strategy = json.loads(STRATEGY_PATH.read_text(encoding="utf-8"))
    for path in _walk(strategy):
        if path.startswith("_comment"):
            continue
        assert path in SAFE_PARAMETERS, (
            f"shipped key {path!r} is not registered in SAFE_PARAMETERS — "
            "experiments would silently drop it"
        )


def test_every_v2_key_loads_and_is_non_default():
    strategy = load_strategy()

    def _get(d, dotted):
        node = d
        for part in dotted.split("."):
            node = node[part]
        return node

    for dotted in V2_KEYS:
        value = _get(strategy, dotted)  # KeyError = the loader dropped it
        assert value is not None, f"{dotted} is None"
        if isinstance(value, bool):
            continue  # booleans are legitimately False/True by design
        assert value != "", f"{dotted} is empty"


def test_v2_tunables_are_experiment_safe():
    """The gates we tune (margin_stop, question caps, coverage weights) must
    be sweepable by the research agent."""
    tunables = {
        "clarification.max_questions_per_session",
        "clarification.min_candidates_before_recommend",
        "clarification.last_question_turn",
        "clarification.margin_stop",
        "ranking.coverage_weight",
        "ranking.coverage_salience_weight",
        "ranking.full_match_bonus",
        "ranking.browsing_popularity_bump",
        "retrieval.guarantee.rerank_floor",
        "retrieval.guarantee.plausible_set_limit",
    }
    assert tunables <= SAFE_PARAMETERS
