"""Central configuration.

Two layers, on purpose:

- **Strategy** (`default_strategy.json`) — retrieval weights, candidate
  limits, clarification policy. This is what `neeshops/research/` tunes
  experimentally. Load it with `load_strategy()`; never hardcode a weight
  inside an algorithm module — read it from here instead.
- **Settings** (env vars, via `.env`) — secrets, paths, feature flags that
  are environment concerns rather than algorithm concerns.

Both are intentionally simple (JSON + os.environ) — no config framework.
"""

from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STRATEGY_PATH = Path(__file__).resolve().parent / "default_strategy.json"


class Settings:
    """Environment-derived settings. Instantiate via `get_settings()`."""

    def __init__(self) -> None:
        self.catalog_path = Path(
            os.getenv("NEESHOPS_CATALOG_PATH", "data/catalog.jsonl")
        )
        self.public_set_path = Path(
            os.getenv("NEESHOPS_PUBLIC_SET_PATH", "data/public_set.jsonl")
        )
        self.log_level = os.getenv("NEESHOPS_LOG_LEVEL", "INFO")

        self.llm_provider = (
            os.getenv("NEESHOPS_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "openrouter"))
            .strip()
            .lower()
        )
        self.llm_model = os.getenv(
            "NEESHOPS_LLM_MODEL", os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
        ).strip()
        self.llm_secondary_provider = (
            os.getenv("NEESHOPS_LLM_SECONDARY_PROVIDER", "gemini").strip().lower()
        )
        self.llm_secondary_model = os.getenv(
            "NEESHOPS_LLM_SECONDARY_MODEL", "gemini-3.7-flash"
        ).strip()
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.openrouter_base = os.getenv(
            "OPENROUTER_API_BASE", "https://openrouter.ai/api/v1/chat/completions"
        ).strip()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

        self.enable_llm_reranker = _bool_env("NEESHOPS_ENABLE_LLM_RERANKER", False)
        self.enable_semantic_retrieval = _bool_env(
            "NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL", False
        )


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_strategy(path: Path | None = None) -> dict[str, Any]:
    """Load the strategy config as a plain dict (deep-copied so callers —
    e.g. an experiment — can mutate their own copy safely)."""
    strategy_path = path or DEFAULT_STRATEGY_PATH
    with open(strategy_path) as f:
        strategy = json.load(f)
    return copy.deepcopy(strategy)
