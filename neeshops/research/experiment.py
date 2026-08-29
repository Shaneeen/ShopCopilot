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
    "retrieval.strategy",
    "retrieval.rrf_k",
    "retrieval.buying.bm25_weight",
    "retrieval.buying.semantic_weight",
    "retrieval.browsing.bm25_weight",
    "retrieval.browsing.semantic_weight",
    "retrieval.candidate_limit",
    "ranking.rerank_limit",
    "ranking.personalization_weight",
    "clarification.max_questions_per_session",
    "clarification.min_candidates_before_recommend",
    "clarification.ask_if_candidates_above",
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
    node[keys[-1]] = value
