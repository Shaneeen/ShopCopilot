"""Proposes new candidate parameter values within SAFE_PARAMETERS.

Stage-1: a placeholder grid/random search over a couple of the most
impactful retrieval weights — deliberately simple. This is the seam where
"analyse weak scenarios -> form a hypothesis -> propose a safe config" would
eventually get smarter (e.g. bayesian optimisation, or an LLM proposing a
hypothesis from scenario-level eval breakdowns). No LLM dependency required
for this backbone.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from neeshops.research.experiment import Experiment

# param_path -> (min, max) search bounds
DEFAULT_SEARCH_SPACE: dict[str, tuple[float, float]] = {
    "retrieval.buying.bm25_weight": (0.4, 0.9),
    "retrieval.browsing.semantic_weight": (0.4, 0.9),
}


def propose_grid(
    param_path: str,
    values: list[float],
    name_prefix: str = "grid",
    hypothesis: Optional[str] = None,
) -> list[Experiment]:
    """One experiment per value in `values` for a single parameter."""
    return [
        Experiment(
            name=f"{name_prefix}::{param_path}={v}",
            hypothesis=hypothesis or f"Varying {param_path} affects ranking quality.",
            parameters={param_path: v},
        )
        for v in values
    ]


def propose_random(
    search_space: Optional[dict[str, tuple[float, float]]] = None,
    n: int = 5,
    seed: Optional[int] = None,
    hypothesis: Optional[str] = None,
) -> list[Experiment]:
    """Sample `n` random single-parameter perturbations from the search
    space — a minimal stand-in for a smarter optimizer."""
    space = search_space or DEFAULT_SEARCH_SPACE
    rng = random.Random(seed)
    experiments = []
    for i in range(n):
        param_path = rng.choice(list(space.keys()))
        lo, hi = space[param_path]
        value = round(rng.uniform(lo, hi), 3)
        experiments.append(
            Experiment(
                name=f"random::{param_path}={value}::{i}",
                hypothesis=hypothesis
                or f"Randomly sampled {param_path}={value} may improve on baseline.",
                parameters={param_path: value},
            )
        )
    return experiments


def next_experiments(scenario_metrics: Optional[dict[str, Any]] = None) -> list[Experiment]:
    """Analyze scenario evaluation metrics, identify the weakest scenario,
    and generate targeted experiments with actionable hypotheses designed
    to fix that specific weakness.
    """
    if not scenario_metrics:
        return propose_random(n=3)

    # Filter only valid scenario dictionaries with metric data
    valid_scenarios = {
        name: metrics
        for name, metrics in scenario_metrics.items()
        if isinstance(metrics, dict) and "hit_rate_at_10" in metrics
    }
    if not valid_scenarios:
        return propose_random(n=3)

    # Sort scenarios to find the weakest by hit_rate_at_10, using MRR as secondary tiebreaker
    weakest_name, weakest_stats = min(
        valid_scenarios.items(),
        key=lambda item: (item[1].get("hit_rate_at_10", 0.0), item[1].get("mrr", 0.0)),
    )

    hit_rate = weakest_stats.get("hit_rate_at_10", 0.0)
    experiments: list[Experiment] = []

    if weakest_name == "browsing":
        experiments.extend([
            Experiment(
                name="targeted::browsing::semantic_weight=0.5",
                hypothesis=f"Browsing weak (HitRate: {hit_rate:.1%}): Lowering semantic weight to balance keyword match for exploratory queries.",
                parameters={"retrieval.browsing.semantic_weight": 0.5},
            ),
            Experiment(
                name="targeted::browsing::semantic_weight=0.85",
                hypothesis=f"Browsing weak (HitRate: {hit_rate:.1%}): Increasing semantic weight to discover broader exploratory items.",
                parameters={"retrieval.browsing.semantic_weight": 0.85},
            ),
            Experiment(
                name="targeted::browsing::min_candidates=8",
                hypothesis=f"Browsing weak (HitRate: {hit_rate:.1%}): Requiring 8 candidates before recommending avoids premature narrow guesses.",
                parameters={"clarification.min_candidates_before_recommend": 8.0},
            ),
        ])
    elif weakest_name == "buying":
        experiments.extend([
            Experiment(
                name="targeted::buying::bm25_weight=0.85",
                hypothesis=f"Buying weak (HitRate: {hit_rate:.1%}): Increasing BM25 weight to sharpen exact constraint matching.",
                parameters={"retrieval.buying.bm25_weight": 0.85},
            ),
            Experiment(
                name="targeted::buying::candidate_limit=300",
                hypothesis=f"Buying weak (HitRate: {hit_rate:.1%}): Expanding candidate pool to 300 to retain strict-constraint products.",
                parameters={"retrieval.candidate_limit": 300.0},
            ),
            Experiment(
                name="targeted::buying::rerank_limit=60",
                hypothesis=f"Buying weak (HitRate: {hit_rate:.1%}): Reranking top 60 items improves precision on budget/spec filters.",
                parameters={"ranking.rerank_limit": 60.0},
            ),
        ])
    elif weakest_name == "intent_override":
        experiments.extend([
            Experiment(
                name="targeted::intent_override::personalization_weight=0.0",
                hypothesis=f"Intent Override weak (HitRate: {hit_rate:.1%}): Zeroing personalization completely eliminates historical profile bias against newly pivoted constraints.",
                parameters={"ranking.personalization_weight": 0.0},
            ),
            Experiment(
                name="targeted::intent_override::candidate_limit=300",
                hypothesis=f"Intent Override weak (HitRate: {hit_rate:.1%}): Expanding candidate limit to 300 ensures pivoted keywords retrieve products despite early turn noise.",
                parameters={"retrieval.candidate_limit": 300},
            ),
            Experiment(
                name="targeted::intent_override::min_candidates=3",
                hypothesis=f"Intent Override weak (HitRate: {hit_rate:.1%}): Lowering candidate threshold before recommendation to 3 allows faster conversion on focused pivot constraints.",
                parameters={"clarification.min_candidates_before_recommend": 3},
            ),
        ])
    elif weakest_name == "boundary":
        experiments.extend([
            Experiment(
                name="targeted::boundary::ask_above=80",
                hypothesis=f"Boundary weak (HitRate: {hit_rate:.1%}): Raising ask threshold to 80 avoids redundant questions on no-preference replies.",
                parameters={"clarification.ask_if_candidates_above": 80.0},
            ),
            Experiment(
                name="targeted::boundary::min_candidates=3",
                hypothesis=f"Boundary weak (HitRate: {hit_rate:.1%}): Recommending earlier from available items when customer has no preference.",
                parameters={"clarification.min_candidates_before_recommend": 3.0},
            ),
            Experiment(
                name="targeted::boundary::personalization_weight=0.25",
                hypothesis=f"Boundary weak (HitRate: {hit_rate:.1%}): Increasing profile boost when in-dialogue constraints are disclaimed.",
                parameters={"ranking.personalization_weight": 0.25},
            ),
        ])
    else:
        return propose_random(n=3)

    return experiments
