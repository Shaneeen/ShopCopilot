"""Retrieval-signal normalization and fusion primitives."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def normalize_scores(scores: Sequence[float], method: str = "minmax") -> list[float]:
    """Normalize scores deterministically; invalid values safely become zero."""
    clean = [_finite_or_zero(score) for score in scores]
    if not clean:
        return []
    if method == "raw":
        return clean
    if method == "minmax":
        low, high = min(clean), max(clean)
        if high == low:
            return [1.0] * len(clean)
        return [(score - low) / (high - low) for score in clean]
    if method == "rank":
        order = sorted(range(len(clean)), key=lambda index: (-clean[index], index))
        if len(clean) == 1:
            return [1.0]
        normalized = [0.0] * len(clean)
        for rank, index in enumerate(order, start=1):
            normalized[index] = 1.0 - (rank - 1) / (len(clean) - 1)
        return normalized
    raise ValueError(f"Unknown retrieval normalization method: {method}")


def reciprocal_rank_fusion(
    source_rankings: Mapping[str, Sequence[str]], *, k: int = 60
) -> dict[str, float]:
    """Return RRF scores from genuine independent, one-based source ranks."""
    if k < 0:
        raise ValueError("RRF k must be non-negative")
    scores: dict[str, float] = {}
    for ranking in source_rankings.values():
        seen: set[str] = set()
        for rank, parent_asin in enumerate(ranking, start=1):
            if not parent_asin or parent_asin in seen:
                continue
            seen.add(parent_asin)
            scores[parent_asin] = scores.get(parent_asin, 0.0) + 1.0 / (k + rank)
    return scores


def _finite_or_zero(value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0
