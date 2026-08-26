"""Semantic (embedding) retrieval — interface + architecture only for
Stage 1. Not required for the baseline to run.

Intended eventual shape: embed the query and the catalog with a sentence
embedding model, index catalog vectors with FAISS (or similar), and return
nearest neighbours as candidates. Gated behind
`NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL` / `enable_semantic_retrieval` so the
baseline agent never depends on the optional `sentence-transformers`/`faiss`
packages.
"""
from __future__ import annotations

from typing import Optional

from neeshops.config.settings import get_settings
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate, Retriever
from neeshops.utils.logging import log_event


class SemanticRetriever(Retriever):
    name = "semantic"

    def __init__(self, index_path: Optional[str] = None) -> None:
        self.index_path = index_path
        self._index = None  # would hold a FAISS index once implemented

    def is_available(self) -> bool:
        settings = get_settings()
        return settings.enable_semantic_retrieval and self._index is not None

    def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
        if not self.is_available():
            log_event("semantic.unavailable", reason="not enabled or index not built")
            return []
        # TODO(Workstream 2): embed `query`, run ANN search against
        # `self._index`, return top_k Candidates with source="semantic".
        raise NotImplementedError(
            "SemanticRetriever is a Stage-1 interface stub. Enable it once an "
            "embedding index exists — see docs/neeshops/ARCHITECTURE.md."
        )
