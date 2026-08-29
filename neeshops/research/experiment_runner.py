"""Runs one Experiment's strategy against a dataset via a supplied
evaluation function, compares it to a baseline, and records the outcome.

Deliberately decoupled from *how* evaluation happens (`evaluate_fn`) so
this module has no hard dependency on the organiser's evaluator — wiring
that in is scripts/run_experiment.py's job (see scripts/evaluate.py for the
wrapper). This keeps `neeshops/research/` testable without the evaluator
present.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from neeshops.research.experiment import Experiment
from neeshops.research.results_store import ResultsStore
from neeshops.utils.logging import log_event

# (strategy_dict, dataset_path) -> metrics dict, e.g.
# {"hit_rate_at_10": .., "mrr": .., "mttc": .., "technical_score": ..}
EvaluateFn = Callable[[dict[str, Any], str], dict[str, float]]

PRIMARY_METRIC = "technical_score"


class ExperimentRunner:
    def __init__(
        self,
        evaluate_fn: EvaluateFn,
        results_store: Optional[ResultsStore] = None,
        min_improvement: float = 0.0,
    ) -> None:
        self.evaluate_fn = evaluate_fn
        self.results_store = results_store or ResultsStore()
        self.min_improvement = min_improvement

    def run(
        self,
        experiment: Experiment,
        dataset_path: str,
        baseline_metrics: dict[str, float],
        base_strategy: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Evaluate `experiment`'s strategy, compare against
        `baseline_metrics`, record + accept/reject on PRIMARY_METRIC.

        Accept iff the candidate's PRIMARY_METRIC beats baseline by at least
        `min_improvement` (absolute). Rejecting is a normal, expected
        outcome — most hypotheses should fail.
        """
        import time

        strategy = experiment.build_strategy(base=base_strategy)

        log_event(
            "experiment.start",
            experiment_id=experiment.experiment_id,
            name=experiment.name,
            parameters=experiment.parameters,
            dataset_path=dataset_path,
        )
        start_time = time.perf_counter()
        candidate_metrics = self.evaluate_fn(strategy, dataset_path)
        latency_seconds = round(time.perf_counter() - start_time, 3)

        baseline_score = baseline_metrics.get(PRIMARY_METRIC, 0.0)
        candidate_score = candidate_metrics.get(PRIMARY_METRIC, 0.0)
        delta = candidate_score - baseline_score
        # Require strictly positive improvement; ties (delta <= 0) and sub-threshold gains are rejected
        accepted = delta > self.min_improvement if self.min_improvement > 0 else delta > 0.0

        tokens = candidate_metrics.get("reported_token_usage", {})
        scenario_metrics = candidate_metrics.get("scenario_metrics", {})

        record = self.results_store.record(
            experiment_id=experiment.experiment_id,
            name=experiment.name,
            hypothesis=experiment.hypothesis,
            dataset_path=dataset_path,
            strategy=strategy,
            latency_seconds=latency_seconds,
            parameters=experiment.parameters,
            metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            tokens=tokens,
            scenario_metrics=scenario_metrics,
            accepted=accepted,
        )
        log_event(
            "experiment.complete",
            experiment_id=experiment.experiment_id,
            accepted=accepted,
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            latency_seconds=latency_seconds,
        )
        return record
