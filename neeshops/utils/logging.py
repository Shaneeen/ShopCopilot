"""Structured logging for the agent pipeline.

Every stage of the pipeline (state update, retrieval, ranking, ...) should
log one structured event via `log_event`, so a session/turn can be
reconstructed from logs alone. Never log secrets (API keys) — settings
already keeps those out of anything passed here.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from neeshops.config.settings import get_settings

_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        stream=sys.stdout,
        format="%(message)s",
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)


_logger = get_logger("neeshops")


def log_event(event: str, **fields: Any) -> None:
    """Emit one structured JSON log line.

    Example:
        log_event("retrieval.completed", session_id=sid, turn=turn,
                   strategy="hybrid", candidate_count=len(candidates),
                   latency_ms=elapsed)
    """
    payload = {"event": event, "ts": time.time(), **fields}
    _logger.info(json.dumps(payload, default=str))
