"""Tests for the strategy-agnostic ranking experiment harness."""
from neeshops.ranking.deterministic import ConstraintAwareRanker, FusionAwareRanker
from neeshops.ranking.experiments import (
    RankingExperimentCase,
    RankingExperimentHarness,
    RetrievalOrderRanker,
)
from neeshops.ranking.heuristic import HeuristicRanker
from tests.ranking_fixtures import (
    SYNTHETIC_BOOT_CANDIDATES,
    SYNTHETIC_BOOT_CATALOG,
    boot_state,
)


def test_same_case_runs_through_registered_r0_r1_r2_r3():
    harness = RankingExperimentHarness()
    harness.register("R0", RetrievalOrderRanker(), {"mode": "identity"})
    harness.register("R1", HeuristicRanker(), {"mode": "existing"})
    harness.register("R2", ConstraintAwareRanker(), {"mode": "constraints"})
    harness.register("R3", FusionAwareRanker(), {"fusion": "minmax"})
    case = RankingExperimentCase(
        case_id="synthetic-material-conflict",
        candidates=SYNTHETIC_BOOT_CANDIDATES,
        catalog_lookup=SYNTHETIC_BOOT_CATALOG,
        state=boot_state(),
        expected_parent_asin="LEATHER_BLACK",
    )

    records = harness.run(case, top_k=3)

    assert [record["strategy_name"] for record in records] == ["R0", "R1", "R2", "R3"]
    assert all(record["case_id"] == case.case_id for record in records)
    assert all(record["synthetic"] is True for record in records)
    assert all(record["input_candidate_count"] == 5 for record in records)
    assert all(record["latency_ms"] >= 0 for record in records)
    assert all(len(record["ranked_top_10"]) <= 3 for record in records)
    assert records[0]["original_retrieval_top_10"] == [
        "SYNTHETIC_BLACK",
        "LEATHER_BLACK",
        "LEATHER_BROWN",
        "LEATHER_HIGH",
        "SNEAKER",
    ]
    assert records[0]["target_rank"] == 2
    assert records[0]["reciprocal_rank"] == 0.5
    assert records[2]["target_rank"] == 1
    assert records[2]["reciprocal_rank"] == 1.0


def test_harness_records_strategy_failure_without_stopping_other_runs():
    class BrokenRanker(RetrievalOrderRanker):
        def rank(self, candidates, catalog_lookup, state, top_k):
            raise RuntimeError("synthetic failure")

    harness = RankingExperimentHarness()
    harness.register("broken", BrokenRanker())
    harness.register("r0", RetrievalOrderRanker())
    case = RankingExperimentCase(
        "failure-case", SYNTHETIC_BOOT_CANDIDATES, SYNTHETIC_BOOT_CATALOG, boot_state()
    )
    records = harness.run(case, top_k=2)
    assert records[0]["error"] == "RuntimeError"
    assert records[0]["ranked_top_10"] == []
    assert records[1]["error"] is None
    assert records[1]["ranked_top_10"]


def test_harness_caps_recorded_rankings_at_ten_and_r0_respects_zero():
    candidates = SYNTHETIC_BOOT_CANDIDATES * 3
    case = RankingExperimentCase(
        "bounded", candidates, SYNTHETIC_BOOT_CATALOG, boot_state()
    )
    harness = RankingExperimentHarness()
    r0 = RetrievalOrderRanker()
    harness.register("r0", r0)
    assert r0.rank(candidates, SYNTHETIC_BOOT_CATALOG, boot_state(), 0) == []
    record = harness.run(case, top_k=100)[0]
    assert len(record["original_retrieval_top_10"]) <= 10
    assert len(record["ranked_top_10"]) <= 10
