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


def test_results_store_records_extended_metadata(tmp_path):
    store = ResultsStore(path=tmp_path / "results.jsonl")
    runner = ExperimentRunner(
        evaluate_fn=lambda strat, path: {
            "technical_score": 0.35,
            "reported_token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "scenario_metrics": {"buying": {"hit_rate_at_10": 0.5}},
        },
        results_store=store,
    )
    experiment = Experiment(name="meta-test", hypothesis="h", parameters={"ranking.personalization_weight": 0.2})
    record = runner.run(
        experiment,
        dataset_path="data/dev_split.jsonl",
        baseline_metrics={"technical_score": 0.2},
    )

    assert record["dataset_path"] == "data/dev_split.jsonl"
    assert "git_commit" in record
    assert record["latency_seconds"] is not None
    assert record["strategy"]["ranking"]["personalization_weight"] == 0.2
    assert record["tokens"]["total_tokens"] == 15
    assert record["scenario_metrics"]["buying"]["hit_rate_at_10"] == 0.5
    assert record["accepted"] is True


def test_runner_rejects_ties(tmp_path):
    experiment = Experiment(
        name="tie-test", hypothesis="x", parameters={"retrieval.candidate_limit": 100}
    )
    runner = ExperimentRunner(
        evaluate_fn=lambda strategy, dataset_path: {"technical_score": 0.25},
        results_store=ResultsStore(path=tmp_path / "results.jsonl"),
    )
    # Candidate score == Baseline score -> TIE -> must be REJECTED
    record = runner.run(experiment, dataset_path="unused", baseline_metrics={"technical_score": 0.25})
    assert record["accepted"] is False


def test_runner_enforces_min_improvement(tmp_path):
    experiment = Experiment(
        name="min-test", hypothesis="x", parameters={"retrieval.candidate_limit": 100}
    )
    runner = ExperimentRunner(
        evaluate_fn=lambda strategy, dataset_path: {"technical_score": 0.252},
        results_store=ResultsStore(path=tmp_path / "results.jsonl"),
        min_improvement=0.005,  # Requires at least +0.005 gain
    )
    # Gain is only +0.002 (< 0.005) -> must be REJECTED
    record = runner.run(experiment, dataset_path="unused", baseline_metrics={"technical_score": 0.250})
    assert record["accepted"] is False


def test_next_experiments_targets_weakest_scenario():
    from neeshops.research.optimizer import next_experiments

    scenario_metrics = {
        "buying": {"hit_rate_at_10": 0.38, "mrr": 0.22},
        "browsing": {"hit_rate_at_10": 0.24, "mrr": 0.16},
        "intent_override": {"hit_rate_at_10": 0.12, "mrr": 0.08},  # WEAKEST
        "boundary": {"hit_rate_at_10": 0.30, "mrr": 0.20},
    }
    experiments = next_experiments(scenario_metrics)
    assert len(experiments) >= 1
    for exp in experiments:
        assert isinstance(exp, Experiment)
        assert "intent_override" in exp.name or "Intent Override" in exp.hypothesis
        assert set(exp.parameters.keys()).issubset(SAFE_PARAMETERS)
        assert len(exp.hypothesis) > 10


def test_next_experiments_fallback_on_empty():
    from neeshops.research.optimizer import next_experiments

    experiments = next_experiments({})
    assert len(experiments) == 3
    for exp in experiments:
        assert isinstance(exp, Experiment)
