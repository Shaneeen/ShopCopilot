"""Merge candidate lists from multiple retrievers into one deduplicated,
weighted-score ranking. Used by HybridRetriever, but kept standalone so it's
independently testable and reusable by the research agent for offline
analysis.
"""
from __future__ import annotations

from neeshops.retrieval.base import Candidate


def merge_weighted(
    candidate_lists: dict[str, list[Candidate]],
    weights: dict[str, float],
) -> list[Candidate]:
    """Combine several retrievers' outputs.

    `candidate_lists`: {"bm25": [...], "semantic": [...]}
    `weights`: {"bm25": 0.7, "semantic": 0.3} — missing weights default to 0.

    Each retriever's raw scores are min-max normalised to [0, 1] first (raw
    BM25 and cosine-similarity scores aren't on comparable scales), then
    combined as a weighted sum. A candidate found by multiple retrievers
    accumulates the weighted contribution from each, and its `source`
    records every retriever that surfaced it.
    """
    merged: dict[str, Candidate] = {}

    for source, candidates in candidate_lists.items():
        weight = weights.get(source, 0.0)
        if weight <= 0 or not candidates:
            continue
        scores = [c.score for c in candidates]
        lo, hi = min(scores), max(scores)
        spread = (hi - lo) or 1.0

        for c in candidates:
            normalized = (c.score - lo) / spread
            contribution = normalized * weight
            if c.parent_asin in merged:
                existing = merged[c.parent_asin]
                existing.score += contribution
                if source not in existing.source.split("+"):
                    existing.source = f"{existing.source}+{source}"
            else:
                merged[c.parent_asin] = Candidate(
                    parent_asin=c.parent_asin, score=contribution, source=source
                )

    return sorted(merged.values(), key=lambda c: c.score, reverse=True)
