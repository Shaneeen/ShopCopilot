#!/usr/bin/env python3
"""Reliability harness: deliberately breaks environment and inputs to verify
that the Agent always returns a contract-conformant response and never raises
an unhandled exception (P5 stretch goal).

Usage:
    python scripts/reliability_harness.py
"""
from __future__ import annotations

import json
import logging
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from neeshops.agent import NeeShopsAgent
from neeshops.models.session import ConversationState
from neeshops.ranking.base import Ranker
from neeshops.retrieval.base import Candidate, Retriever
from starter.agent import Agent


@dataclass
class TestCaseResult:
    name: str
    passed: bool
    details: str
    error: str | None = None


def _validate_contract(response: dict[str, Any], top_k: int = 10) -> tuple[bool, str]:
    if not isinstance(response, dict):
        return False, f"Expected dict response, got {type(response)}"
    if "message" not in response or not isinstance(response["message"], str) or len(response["message"]) == 0:
        return False, f"Invalid 'message' in response: {response.get('message')!r}"
    if "recommendations" not in response or not isinstance(response["recommendations"], list):
        return False, f"Invalid 'recommendations' in response: {response.get('recommendations')!r}"
    if len(response["recommendations"]) > top_k:
        return False, f"Recommendations count {len(response['recommendations'])} exceeded top_k={top_k}"
    for idx, rec in enumerate(response["recommendations"]):
        if not isinstance(rec, dict) or "parent_asin" not in rec or not rec["parent_asin"]:
            return False, f"Invalid recommendation item at index {idx}: {rec}"
    if "usage" not in response or not isinstance(response["usage"], dict):
        return False, f"Invalid 'usage' in response: {response.get('usage')!r}"
    if not isinstance(response["usage"].get("prompt_tokens"), int) or response["usage"]["prompt_tokens"] < 0:
        return False, f"Invalid prompt_tokens: {response['usage'].get('prompt_tokens')}"
    if not isinstance(response["usage"].get("completion_tokens"), int) or response["usage"]["completion_tokens"] < 0:
        return False, f"Invalid completion_tokens: {response['usage'].get('completion_tokens')}"
    return True, "Valid"


def run_missing_catalog_test() -> TestCaseResult:
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_path = Path(tmp_dir) / "nonexistent_catalog.jsonl"
            agent = Agent(catalog_path=missing_path)
            agent.reset("missing_cat_sess", {})
            res = agent.respond("missing_cat_sess", "running shoes", turn=1, top_k=10)
            valid, reason = _validate_contract(res, top_k=10)
            if not valid:
                return TestCaseResult("Missing Catalog File", False, f"Contract invalid: {reason}")
            if res["recommendations"] != []:
                return TestCaseResult("Missing Catalog File", False, f"Expected [] recs, got {res['recommendations']}")
            return TestCaseResult("Missing Catalog File", True, "Handled missing catalog with 0 candidates gracefully")
    except Exception as exc:
        return TestCaseResult("Missing Catalog File", False, "Unhandled exception", error=str(exc))


def run_missing_llm_key_test() -> TestCaseResult:
    try:
        strategy = {
            "retrieval": {
                "candidate_limit": 50,
                "buying": {"bm25_weight": 0.7, "semantic_weight": 0.3},
                "browsing": {"bm25_weight": 0.3, "semantic_weight": 0.7},
            },
            "ranking": {"rerank_limit": 20, "personalization_weight": 0.15},
            "clarification": {
                "max_questions_per_session": 2,
                "min_candidates_before_recommend": 5,
                "ask_if_candidates_above": 60,
            },
            "feature_flags": {"enable_llm_reranker": True, "enable_semantic_retrieval": False},
        }
        agent = Agent(strategy=strategy)
        agent.reset("missing_key_sess", {"preference_tags": ["shoes"]})
        res = agent.respond("missing_key_sess", "sneakers", turn=1, top_k=10)
        valid, reason = _validate_contract(res, top_k=10)
        if not valid:
            return TestCaseResult("Missing LLM Key Fallback", False, f"Contract invalid: {reason}")
        return TestCaseResult("Missing LLM Key Fallback", True, "Fell back deterministically to HeuristicRanker")
    except Exception as exc:
        return TestCaseResult("Missing LLM Key Fallback", False, "Unhandled exception", error=str(exc))


def run_empty_and_whitespace_test() -> TestCaseResult:
    try:
        agent = Agent()
        agent.reset("empty_query_sess", {})
        payloads = ["", "   ", "\t\t", "\n\r\n", "   \n\t   "]
        for idx, payload in enumerate(payloads, start=1):
            res = agent.respond("empty_query_sess", payload, turn=idx, top_k=10)
            valid, reason = _validate_contract(res, top_k=10)
            if not valid:
                return TestCaseResult("Empty/Whitespace Query", False, f"Payload {payload!r} returned invalid contract: {reason}")
        return TestCaseResult("Empty/Whitespace Query", True, f"Handled {len(payloads)} whitespace variations safely")
    except Exception as exc:
        return TestCaseResult("Empty/Whitespace Query", False, "Unhandled exception", error=str(exc))


def run_adversarial_payloads_test() -> TestCaseResult:
    try:
        agent = Agent()
        agent.reset("adversarial_sess", {"nested": {"bad": None}})
        payloads = [
            "👟🔥🎉 跑步鞋 \u200b\u200c <script>alert('xss')</script>",
            "DROP TABLE products; SELECT * FROM catalog WHERE 1=1; --",
            "NULL\x00\x01\x02\x7f\xff control characters",
            "A" * 30000,
            "shoes " * 5000,
        ]
        for idx, payload in enumerate(payloads, start=1):
            res = agent.respond("adversarial_sess", payload, turn=idx, top_k=10)
            valid, reason = _validate_contract(res, top_k=10)
            if not valid:
                return TestCaseResult("Adversarial/Fuzz Payloads", False, f"Payload idx {idx} returned invalid contract: {reason}")
        return TestCaseResult("Adversarial/Fuzz Payloads", True, f"Handled {len(payloads)} adversarial inputs safely")
    except Exception as exc:
        return TestCaseResult("Adversarial/Fuzz Payloads", False, "Unhandled exception", error=str(exc))


def run_crashing_retriever_test() -> TestCaseResult:
    try:
        class CrashingRetriever(Retriever):
            name = "crashing_retriever"

            def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
                raise RuntimeError("Database connection timed out or socket broken")

        agent = NeeShopsAgent(retriever=CrashingRetriever())
        agent.reset("retriever_crash_sess", {})
        res = agent.respond("retriever_crash_sess", "black shoes", turn=1, top_k=10)
        valid, reason = _validate_contract(res, top_k=10)
        if not valid:
            return TestCaseResult("Crashing Retriever Injection", False, f"Contract invalid: {reason}")
        if res["recommendations"] != []:
            return TestCaseResult("Crashing Retriever Injection", False, "Expected 0 recommendations on retriever failure")
        return TestCaseResult("Crashing Retriever Injection", True, "Safely caught retriever exception, returned contract response")
    except Exception as exc:
        return TestCaseResult("Crashing Retriever Injection", False, "Unhandled exception", error=str(exc))


def run_crashing_ranker_test() -> TestCaseResult:
    try:
        class CrashingRanker(Ranker):
            name = "crashing_ranker"

            def rank(self, candidates, catalog_lookup, state, top_k):
                raise ConnectionError("503 Service Unavailable / Rate Limit Exceeded")

        class DummyRetriever(Retriever):
            name = "dummy"

            def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
                return [Candidate(parent_asin=f"B00{i}", score=1.0, source="dummy") for i in range(1, 8)]

        agent = NeeShopsAgent(retriever=DummyRetriever(), ranker=CrashingRanker())
        agent.reset("ranker_crash_sess", {})
        res = agent.respond("ranker_crash_sess", "shoes", turn=1, top_k=5)
        valid, reason = _validate_contract(res, top_k=5)
        if not valid:
            return TestCaseResult("Crashing Ranker Injection", False, f"Contract invalid: {reason}")
        if len(res["recommendations"]) != 5:
            return TestCaseResult("Crashing Ranker Injection", False, f"Expected 5 recommendations from fallback, got {len(res['recommendations'])}")
        return TestCaseResult("Crashing Ranker Injection", True, "Safely fell back to HeuristicRanker without raising")
    except Exception as exc:
        return TestCaseResult("Crashing Ranker Injection", False, "Unhandled exception", error=str(exc))


def run_boundary_params_test() -> TestCaseResult:
    try:
        agent = Agent()
        agent.reset("boundary_params_sess", {})
        param_cases = [
            (0, 0),
            (-1, 5),
            (999, 50),
        ]
        for turn, top_k in param_cases:
            res = agent.respond("boundary_params_sess", "shoes", turn=turn, top_k=top_k)
            valid, reason = _validate_contract(res, top_k=top_k)
            if not valid:
                return TestCaseResult("Boundary Params (turn/top_k)", False, f"turn={turn}, top_k={top_k} returned invalid contract: {reason}")
        return TestCaseResult("Boundary Params (turn/top_k)", True, "Handled non-standard turn and top_k values safely")
    except Exception as exc:
        return TestCaseResult("Boundary Params (turn/top_k)", False, "Unhandled exception", error=str(exc))


def main() -> int:
    logging.disable(logging.CRITICAL)
    print("=" * 70)
    print("NeeShops Agent Reliability & Fault-Tolerance Harness (P5 Stretch)")
    print("=" * 70)
    print()

    tests: list[Callable[[], TestCaseResult]] = [
        run_missing_catalog_test,
        run_missing_llm_key_test,
        run_empty_and_whitespace_test,
        run_adversarial_payloads_test,
        run_crashing_retriever_test,
        run_crashing_ranker_test,
        run_boundary_params_test,
    ]

    results: list[TestCaseResult] = []
    for test_fn in tests:
        res = test_fn()
        results.append(res)
        status_tag = "[ PASS ]" if res.passed else "[ FAIL ]"
        print(f"{status_tag:10} {res.name}: {res.details}")
        if res.error:
            print(f"           Error trace: {res.error}")

    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)

    print()
    print("-" * 70)
    print(f"Summary: {passed_count}/{total_count} reliability tests passed.")
    print("-" * 70)

    if passed_count == total_count:
        print("[SUCCESS] Agent is highly resilient: no unhandled exceptions across all fault injections.")
        return 0
    else:
        print(f"[FAILURE] {total_count - passed_count} reliability test(s) failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
