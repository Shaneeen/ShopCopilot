"""Merge candidate lists from multiple retrievers into one deduplicated,
weighted-score ranking. Used by HybridRetriever, but kept standalone so it's
independently testable and reusable by the research agent for offline
analysis.

Every merge function also stamps retrieval provenance (per-source raw
score + per-source rank, plus the final merged rank) onto each Candidate's
optional `metadata` dict — P3 ranks the merged pool but can reason about
recall/diagnose ranking problems without reconstructing per-source ordering
from the merged score. The Candidate 3-field contract is unchanged.
"""
from __future__ import annotations

from neeshops.retrieval.base import Candidate

DEFAULT_RRF_K = 60


def _attach_source(prov: dict, source: str, raw_score: float, rank: int) -> None:
    """Record one source's provenance on the accumulating per-asin dict."""
    prov[source] = {"raw_score": float(raw_score), "rank": rank}


def _stamp_final_rank(merged: list[Candidate]) -> None:
    """Stamp the 1-based position in the final merged order — this is the
    final retrieval rank, so `metadata["rank"]` always agrees with list
    position."""
    for i, c in enumerate(merged, start=1):
        if not isinstance(c.metadata, dict):
            c.metadata = {}
        c.metadata["rank"] = i


def _tie_break(c: Candidate) -> tuple[float, str]:
    """Deterministic ordering for exact score ties (score desc, asin asc)."""
    return (-c.score, c.parent_asin)


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
    records every retriever that surfaced it. The raw (unnormalised) score
    and 1-based rank within each source's own list survive in
    `candidate.metadata`.
    """
    merged: dict[str, Candidate] = {}

    for source, candidates in candidate_lists.items():
        weight = weights.get(source, 0.0)
        if weight <= 0 or not candidates:
            continue
        scores = [c.score for c in candidates]
        lo, hi = min(scores), max(scores)
        spread = (hi - lo) or 1.0

        for rank, c in enumerate(candidates, start=1):
            normalized = (c.score - lo) / spread
            contribution = normalized * weight
            if c.parent_asin in merged:
                existing = merged[c.parent_asin]
                existing.score += contribution
                if source not in existing.source.split("+"):
                    existing.source = f"{existing.source}+{source}"
            else:
                merged[c.parent_asin] = Candidate(
                    parent_asin=c.parent_asin,
                    score=contribution,
                    source=source,
                    metadata={},
                )
            _attach_source(merged[c.parent_asin].metadata, source, c.score, rank)

    ordered = sorted(merged.values(), key=_tie_break)
    _stamp_final_rank(ordered)
    return ordered


def merge_rrf(
    candidate_lists: dict[str, list[Candidate]],
    weights: dict[str, float],
    k: int = DEFAULT_RRF_K,
) -> list[Candidate]:
    """Reciprocal Rank Fusion — an alternative to `merge_weighted` for the
    "fused" retrieval strategy (P2-D).

    score(asin) = sum over sources of  weight_s / (k + rank_s)

    Rank-based, so no score normalisation is needed and incomparable raw
    scales can't skew the fusion. `k` dampens the head of each list
    (standard k=60); per-route weights still let `buying`/`browsing` favour
    a retriever. Dedup and `source` concatenation behave exactly like
    `merge_weighted`, and provenance (raw score + rank per source, final
    rank) is stamped the same way. Exact ties break on `parent_asin`.
    """
    merged: dict[str, Candidate] = {}

    for source, candidates in candidate_lists.items():
        weight = weights.get(source, 0.0)
        if weight <= 0 or not candidates:
            continue
        for rank, c in enumerate(candidates, start=1):
            contribution = weight / (k + rank)
            if c.parent_asin in merged:
                existing = merged[c.parent_asin]
                existing.score += contribution
                if source not in existing.source.split("+"):
                    existing.source = f"{existing.source}+{source}"
            else:
                merged[c.parent_asin] = Candidate(
                    parent_asin=c.parent_asin,
                    score=contribution,
                    source=source,
                    metadata={},
                )
            _attach_source(merged[c.parent_asin].metadata, source, c.score, rank)

    ordered = sorted(merged.values(), key=_tie_break)
    _stamp_final_rank(ordered)
    return ordered


def stamp_provenance(candidates: list[Candidate], source: str) -> list[Candidate]:
    """Attach retrieval provenance to a single-retriever result list — used
    by the `bm25_only` / `semantic_only` strategies where no merge happens
    but P3 still needs raw score, per-source rank and final rank."""
    for rank, c in enumerate(candidates, start=1):
        prov = c.metadata if isinstance(c.metadata, dict) else {}
        _attach_source(prov, source, c.score, rank)
        c.metadata = prov
    _stamp_final_rank(candidates)
    return candidates
