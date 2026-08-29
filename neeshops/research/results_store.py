"""Append-only experiment history, one JSON object per line.

Stored under artifacts/experiments/ (gitignored — see .gitignore) so raw
experiment output never bloats the repo; docs/neeshops/EXPERIMENTS.md is where a
human-curated summary of *accepted* experiments should live instead.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

DEFAULT_STORE_PATH = Path("artifacts/experiments/results.jsonl")


def get_git_commit_hash() -> str:
    import subprocess
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


class ResultsStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DEFAULT_STORE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        experiment_id: str,
        name: str,
        hypothesis: str,
        parameters: dict[str, Any],
        metrics: dict[str, float],
        baseline_metrics: dict[str, float],
        accepted: bool,
        dataset_path: Optional[str] = None,
        git_commit: Optional[str] = None,
        strategy: Optional[dict[str, Any]] = None,
        latency_seconds: Optional[float] = None,
        tokens: Optional[dict[str, int]] = None,
        scenario_metrics: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        record = {
            "experiment_id": experiment_id,
            "name": name,
            "hypothesis": hypothesis,
            "dataset_path": dataset_path,
            "git_commit": git_commit or get_git_commit_hash(),
            "strategy": strategy,
            "latency_seconds": latency_seconds,
            "parameters": parameters,
            "metrics": metrics,
            "baseline_metrics": baseline_metrics,
            "tokens": tokens or {},
            "scenario_metrics": scenario_metrics or {},
            "accepted": accepted,
            "timestamp": time.time(),
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return record

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def accepted(self) -> list[dict[str, Any]]:
        return [r for r in self.all() if r.get("accepted")]
