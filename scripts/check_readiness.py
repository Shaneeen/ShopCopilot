#!/usr/bin/env python3
"""Explain whether a checkout is ready for NeeShops development.

This is intentionally a diagnostic command: it does not download, generate,
or modify anything.

    python scripts/check_readiness.py
"""
from __future__ import annotations

import importlib.util
import json
import logging
import platform
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SET_PATH = REPO_ROOT / "data" / "public_set.jsonl"
CATALOG_PATH = REPO_ROOT / "data" / "catalog.jsonl"
EXPECTED_SCENARIOS = {
    "buying": 80,
    "browsing": 80,
    "intent_override": 30,
    "boundary": 10,
}


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str
    required: bool = True


def _python_check() -> Check:
    version = sys.version_info
    okay = version >= (3, 10)
    return Check(
        "PASS" if okay else "FAIL",
        "Python version",
        f"{platform.python_version()} (requires 3.10+)",
    )


def _dependency_checks() -> list[Check]:
    checks = []
    for import_name, display_name in (
        ("dotenv", "python-dotenv"),
        ("pydantic", "pydantic"),
        ("pytest", "pytest"),
    ):
        installed = importlib.util.find_spec(import_name) is not None
        checks.append(
            Check(
                "PASS" if installed else "FAIL",
                f"Dependency: {display_name}",
                "installed" if installed else "missing; run pip install -r requirements.txt",
            )
        )
    return checks


def _public_set_check(path: Path = PUBLIC_SET_PATH) -> Check:
    if not path.exists():
        return Check("FAIL", "Public sessions", f"missing: {path}")
    try:
        rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
        counts = Counter(str(row.get("scenario_type")) for row in rows)
    except (OSError, json.JSONDecodeError) as exc:
        return Check("FAIL", "Public sessions", f"could not read JSONL: {exc}")
    okay = len(rows) == 200 and counts == EXPECTED_SCENARIOS
    detail = f"{len(rows)} rows; scenarios={dict(counts)}"
    return Check("PASS" if okay else "FAIL", "Public sessions", detail)


def _catalog_check(path: Path = CATALOG_PATH) -> Check:
    if not path.exists():
        return Check(
            "FAIL",
            "Official catalog",
            "missing; run python scripts/download_catalog.py",
        )
    try:
        row_count = 0
        seen: set[str] = set()
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                parent_asin = str(row["parent_asin"])
                if parent_asin in seen:
                    return Check(
                        "FAIL", "Official catalog", f"duplicate parent_asin at line {line_number}"
                    )
                seen.add(parent_asin)
                row_count += 1
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        return Check("FAIL", "Official catalog", f"could not validate JSONL: {exc}")
    okay = row_count == 50_000
    return Check(
        "PASS" if okay else "FAIL",
        "Official catalog",
        f"{row_count:,} rows and {len(seen):,} unique product IDs (expected 50,000)",
    )


def _agent_import_check() -> Check:
    sys.path.insert(0, str(REPO_ROOT))
    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        from starter.agent import Agent  # noqa: PLC0415

        agent = Agent(CATALOG_PATH)
        agent.reset("readiness-check", {})
    except Exception as exc:  # readiness output should explain any import/setup failure
        return Check("FAIL", "Agent import/reset", f"{type(exc).__name__}: {exc}")
    finally:
        logging.disable(previous_disable_level)
    return Check("PASS", "Agent import/reset", "starter.agent.Agent loaded and reset successfully")


def _optional_feature_checks() -> list[Check]:
    sentence_transformers = importlib.util.find_spec("sentence_transformers") is not None
    llm_sdk = any(importlib.util.find_spec(name) is not None for name in ("openai", "anthropic"))
    return [
        Check(
            "PASS" if sentence_transformers else "INFO",
            "Semantic retrieval dependency",
            "sentence-transformers installed"
            if sentence_transformers
            else "not installed yet; required when P2 implements semantic retrieval",
            required=False,
        ),
        Check(
            "PASS" if llm_sdk else "INFO",
            "LLM reranker dependency",
            "an OpenAI or Anthropic SDK is installed"
            if llm_sdk
            else "not installed yet; required only when P3 implements the LLM reranker",
            required=False,
        ),
    ]


def collect_checks() -> list[Check]:
    checks = [
        _python_check(),
        *_dependency_checks(),
        _public_set_check(),
        _catalog_check(),
    ]
    if all(check.status == "PASS" for check in checks if check.required):
        checks.append(_agent_import_check())
    else:
        checks.append(
            Check(
                "SKIP",
                "Agent import/reset",
                "fix the required setup failures above first",
            )
        )
    checks.extend(_optional_feature_checks())
    return checks


def main() -> int:
    checks = collect_checks()
    print("NeeShops readiness check\n")
    for check in checks:
        print(f"[{check.status:4}] {check.name}: {check.detail}")
    failures = [check for check in checks if check.required and check.status == "FAIL"]
    if failures:
        print(f"\nNot ready: fix {len(failures)} required item(s), then run this command again.")
        return 1
    print("\nReady for development. Next: pytest -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
