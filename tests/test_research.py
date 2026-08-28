"""Research framework: safe-parameter enforcement, strategy building, and
accept/reject wiring — all without touching the real evaluator."""
import pytest

from neeshops.research.experiment import SAFE_PARAMETERS, Experiment
from neeshops.research.experiment_runner import ExperimentRunner
from neeshops.research.results_store import ResultsStore


def test_experiment_rejects_unsafe_parameter():
    with pytest.raises(ValueError):
        Experiment(
            name="bad",
            hypothesis="x",
            parameters={"some.made.up.path": 1.0},
        )


def test_experiment_accepts_declared_safe_parameter():
    param = next(iter(SAFE_PARAMETERS))
    experiment = Experiment(name="ok", hypothesis="x", parameters={param: 0.5})
    assert experiment.experiment_id


def test_build_strategy_overrides_only_the_named_path():
    experiment = Experiment(
        name="weight-test",
        hypothesis="x",
        parameters={"retrieval.buying.bm25_weight": 0.99},
    )
    base = {
        "retrieval": {"buying": {"bm25_weight": 0.7, "semantic_weight": 0.3}},
        "ranking": {"rerank_limit": 40},
    }
    strategy = experiment.build_strategy(base=base)

    assert strategy["retrieval"]["buying"]["bm25_weight"] == 0.99
    assert strategy["retrieval"]["buying"]["semantic_weight"] == 0.3  # untouched
    assert base["retrieval"]["buying"]["bm25_weight"] == 0.7  # base not mutated


def test_runner_accepts_when_candidate_beats_baseline(tmp_path):
    experiment = Experiment(
        name="better", hypothesis="x", parameters={"retrieval.candidate_limit": 100}
    )
    runner = ExperimentRunner(
        evaluate_fn=lambda strategy, dataset_path: {"technical_score": 0.5},
        results_store=ResultsStore(path=tmp_path / "results.jsonl"),
    )
    record = runner.run(experiment, dataset_path="unused", baseline_metrics={"technical_score": 0.1})
    assert record["accepted"] is True


def test_runner_rejects_when_candidate_does_not_beat_baseline(tmp_path):
    experiment = Experiment(
        name="worse", hypothesis="x", parameters={"retrieval.candidate_limit": 100}
    )
    runner = ExperimentRunner(
        evaluate_fn=lambda strategy, dataset_path: {"technical_score": 0.05},
        results_store=ResultsStore(path=tmp_path / "results.jsonl"),
    )
    record = runner.run(experiment, dataset_path="unused", baseline_metrics={"technical_score": 0.1})
    assert record["accepted"] is False


def test_runner_rejects_a_tie_even_when_minimum_improvement_is_zero(tmp_path):
    experiment = Experiment(
        name="tie", hypothesis="x", parameters={"retrieval.candidate_limit": 100}
    )
    runner = ExperimentRunner(
        evaluate_fn=lambda strategy, dataset_path: {"technical_score": 0.1},
        results_store=ResultsStore(path=tmp_path / "results.jsonl"),
    )
    record = runner.run(
        experiment, dataset_path="unused", baseline_metrics={"technical_score": 0.1}
    )
    assert record["accepted"] is False


def test_results_store_persists_and_filters_accepted(tmp_path):
    store = ResultsStore(path=tmp_path / "results.jsonl")
    store.record(
        experiment_id="e1", name="a", hypothesis="h", parameters={},
        metrics={"technical_score": 0.2}, baseline_metrics={"technical_score": 0.1},
        accepted=True,
    )
    store.record(
        experiment_id="e2", name="b", hypothesis="h", parameters={},
        metrics={"technical_score": 0.05}, baseline_metrics={"technical_score": 0.1},
        accepted=False,
    )
    assert len(store.all()) == 2
    assert [r["experiment_id"] for r in store.accepted()] == ["e1"]
