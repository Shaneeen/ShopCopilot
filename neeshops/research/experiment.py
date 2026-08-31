"""An Experiment is a named, dot-path override of the strategy config
(default_strategy.json) plus a hypothesis — never a code change. This is
what keeps the research agent "controlled": it can only ever propose
different values for parameters we've already declared safe to tune.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any

from neeshops.config.settings import load_strategy

# Parameters the research agent is allowed to touch. Anything not listed
# here is rejected in Experiment.__post_init__ — extend deliberately.
# retrieval.strategy / retrieval.rrf_k let experiments compare the P2
# retrieval strategies (bm25_only / semantic_only / hybrid / fused).
SAFE_PARAMETERS = {
    # retrieval
    "retrieval.strategy",
    "retrieval.rrf_k",
    "retrieval.candidate_limit",
    "retrieval.empty_query_fallback",
    "retrieval.buying.bm25_weight",
    "retrieval.buying.semantic_weight",
    "retrieval.browsing.bm25_weight",
    "retrieval.browsing.semantic_weight",
    "retrieval.guarantee.enabled",
    "retrieval.guarantee.slots",
    "retrieval.guarantee.rerank_floor",
    "retrieval.guarantee.plausible_set_limit",
    "retrieval.min_pool_topup",
    "retrieval.multi_query.enabled",
    "retrieval.multi_query.weights.accumulated",
    "retrieval.multi_query.weights.latest",
    "retrieval.multi_query.weights.constraints",
    "retrieval.bm25_field_weights.parent_asin",
    "retrieval.bm25_field_weights.title",
    "retrieval.bm25_field_weights.categories",
    "retrieval.bm25_field_weights.features",
    "retrieval.bm25_field_weights.details",
    "retrieval.bm25_field_weights.store",
    "retrieval.bm25_field_weights.description",
    # ranking (top-level)
    "ranking.rerank_limit",
    "ranking.personalization_weight",
    "ranking.coverage_weight",
    "ranking.coverage_salience_weight",
    "ranking.buying_salience_weight",
    "ranking.buying_popularity_scale",
    "ranking.full_match_bonus",
    "ranking.browsing_popularity_bump",
    "ranking.overlap_dampening_threshold",
    # ranking.deterministic
    "ranking.deterministic.rerank_limit",
    "ranking.deterministic.retrieval_normalization",
    "ranking.deterministic.fusion_method",
    "ranking.deterministic.rrf_k",
    "ranking.deterministic.budget_tolerance",
    "ranking.deterministic.weights.retrieval",
    "ranking.deterministic.weights.category",
    "ranking.deterministic.weights.title_overlap",
    "ranking.deterministic.weights.feature_overlap",
    "ranking.deterministic.weights.color",
    "ranking.deterministic.weights.material",
    "ranking.deterministic.weights.brand",
    "ranking.deterministic.weights.style",
    "ranking.deterministic.weights.size",
    "ranking.deterministic.weights.budget",
    "ranking.deterministic.weights.personalization",
    "ranking.deterministic.weights.inferred",
    "ranking.deterministic.features_enabled.retrieval",
    "ranking.deterministic.features_enabled.category",
    "ranking.deterministic.features_enabled.title_overlap",
    "ranking.deterministic.features_enabled.feature_overlap",
    "ranking.deterministic.features_enabled.color",
    "ranking.deterministic.features_enabled.material",
    "ranking.deterministic.features_enabled.brand",
    "ranking.deterministic.features_enabled.style",
    "ranking.deterministic.features_enabled.size",
    "ranking.deterministic.features_enabled.budget",
    "ranking.deterministic.features_enabled.personalization",
    "ranking.deterministic.features_enabled.inferred",
    "ranking.deterministic.features_enabled.coverage",
    "ranking.deterministic.features_enabled.full_match_bonus",
    "ranking.deterministic.features_enabled.popularity",
    # ranking.llm (tier-2 rerank, default off)
    "ranking.llm.provider",
    "ranking.llm.model",
    "ranking.llm.secondary_provider",
    "ranking.llm.secondary_model",
    "ranking.llm.rerank_limit",
    "ranking.llm.minimum_constraints",
    "ranking.llm.timeout_seconds",
    "ranking.llm.gate_margin",
    "ranking.llm.gate_twins",
    "ranking.llm.blend_epsilon",
    # clarification
    "clarification.strategy",
    "clarification.max_questions_per_session",
    "clarification.min_candidates_before_recommend",
    "clarification.ask_if_candidates_above",
    "clarification.other_max_asks",
    "clarification.last_question_turn",
    "clarification.margin_stop",
    "clarification.entropy_top_k",
    "clarification.entropy_plausible_limit",
    "clarification.entropy_row_cap",
    "clarification.stop_after_no_disclosure",
    # intent (slot lifecycle)
    "intent.route_flip_erase_weight",
    "intent.inferred_decay",
    # filters
    "filters.budget_tolerance",
    "filters.min_pool_keep",
    # feature flags
    "feature_flags.enable_semantic_retrieval",
    "feature_flags.enable_llm_reranker",
}


@dataclass
class Experiment:
    name: str
    hypothesis: str
    parameters: dict[str, Any]
    """Dot-path -> new value, e.g. {"browsing.semantic_weight": 0.65}
    or {"retrieval.strategy": "fused"}."""
    experiment_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def __post_init__(self) -> None:
        unsafe = set(self.parameters) - SAFE_PARAMETERS
        if unsafe:
            raise ValueError(
                f"Experiment '{self.name}' touches parameters outside SAFE_PARAMETERS: "
                f"{sorted(unsafe)}. Add them to SAFE_PARAMETERS deliberately if intended."
            )

    def build_strategy(self, base: dict | None = None) -> dict:
        """Return a full strategy dict with this experiment's overrides
        applied on top of `base` (defaults to the checked-in default
        strategy). Does not mutate the base."""
        strategy = copy.deepcopy(base) if base is not None else load_strategy()
        for dotted_path, value in self.parameters.items():
            _set_dotted(strategy, dotted_path, value)
        return strategy


def _set_dotted(d: dict, dotted_path: str, value) -> None:
    keys = dotted_path.split(".")
    node = d
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    last_key = keys[-1]
    if (
        last_key in node
        and isinstance(node[last_key], int)
        and isinstance(value, (int, float))
    ):
        node[last_key] = int(value)
    else:
        node[last_key] = value
