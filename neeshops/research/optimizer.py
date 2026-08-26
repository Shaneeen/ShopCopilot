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


def next_experiments(scenario_metrics: dict[str, Any]) -> list[Experiment]:
    """TODO(Workstream 4): given per-scenario eval breakdowns (e.g. weak
    Hit Rate@10 on 'browsing' scenarios), pick the parameter most likely to
    help and propose a targeted experiment instead of a random one.

    Stage-1 falls back to a small random batch so the pipeline is runnable
    end-to-end without this analysis being implemented yet.
    """
    return propose_random(n=3)
