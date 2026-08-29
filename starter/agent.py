"""Thin adapter satisfying the official evaluator's required import:

    from starter.agent import Agent

This file is intentionally small: it constructs a `neeshops.agent.
NeeShopsAgent` and translates between its (richer, internal) response shape
and the official Agent API contract in `docs/agent_api_contract.json`. All
real logic lives in `neeshops/` — see `docs/neeshops/ARCHITECTURE.md`.

Constructor signature matches the organiser's original weak baseline
(`Agent(catalog_path: str | Path = "data/catalog.jsonl")`), since
`evaluator/local_evaluator.py` instantiates it positionally as
`Agent(args.catalog)`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from neeshops.agent import NeeShopsAgent
from neeshops.retrieval.bm25 import BM25Retriever
from neeshops.retrieval.hybrid import HybridRetriever
from neeshops.utils.catalog import load_catalog_lookup


class Agent:
    """Required interface (per docs/agent_api_contract.json):

        reset(session_id: str, user_profile: dict) -> None
        respond(session_id: str, user_message: str, turn: int, top_k: int) -> dict

    `catalog_path` is positional to match the organiser's original weak
    baseline signature (`evaluator/local_evaluator.py` calls
    `Agent(args.catalog)`). `strategy` is a NeeShops-only extension (keyword,
    optional, defaults to `neeshops/config/default_strategy.json`) that lets
    `scripts/run_experiment.py` evaluate a candidate config without touching
    this file — the official evaluator never passes it.
    """

    def __init__(
        self,
        catalog_path: Union[str, Path] = "data/catalog.jsonl",
        strategy: Optional[dict[str, Any]] = None,
    ) -> None:
        catalog_path = Path(catalog_path)
        bm25 = BM25Retriever(catalog_path=catalog_path)
        retriever = HybridRetriever(bm25=bm25, strategy=strategy)
        catalog_lookup = load_catalog_lookup(catalog_path)
        self._impl = NeeShopsAgent(
            retriever=retriever, catalog_lookup=catalog_lookup, strategy=strategy
        )

    def reset(self, session_id: str, user_profile: dict) -> None:
        self._impl.reset(session_id, user_profile)

    def respond(
        self,
        session_id: str,
        user_message: str,
        turn: int,
        top_k: int,
    ) -> dict:
        result = self._impl.respond(session_id, user_message, turn, top_k)

        # Conform strictly to docs/agent_api_contract.json's turn_response
        # schema (additionalProperties: false) — NeeShopsAgent's internal
        # response carries extra fields (route, per-item reason) that are
        # useful for our own logging/frontend but not part of the contract.
        recs = [
            {"parent_asin": rec["parent_asin"], "score": rec["score"]}
            if "score" in rec and rec["score"] is not None
            else {"parent_asin": rec["parent_asin"]}
            for rec in result.get("recommendations", [])
            if isinstance(rec, dict) and "parent_asin" in rec
        ]
        if top_k is not None and top_k >= 0:
            recs = recs[:top_k]

        return {
            "message": str(result.get("message") or "Tell me a bit more about what you're looking for."),
            "ask_attribute": result.get("ask_attribute"),
            "recommendations": recs,
            "usage": result.get("usage", {"prompt_tokens": 0, "completion_tokens": 0}),
        }

