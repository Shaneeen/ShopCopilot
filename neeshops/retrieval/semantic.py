"""Semantic (embedding) retrieval — lightweight in-memory implementation.

Design (per the P2 workstream spec's build order): a **hashed TF-IDF +
numpy cosine** baseline rather than `sentence-transformers`, so the only
new dependency is `numpy` — no model download, no torch, comfortably under
the <2B-parameter limit, and per-turn search latency in single-digit
milliseconds even on the 50k catalog. The contract is identical to a
neural encoder: `scripts/build_semantic_index.py` embeds the catalog once
and persists it; `SemanticRetriever` embeds the query with the same
vectorizer and returns nearest neighbours by cosine similarity. Swapping in
`all-MiniLM-L6-v2` later means replacing `_embed_tokens`/`build_index`
bodies — the retriever interface, gating and fail-soft behaviour stay.

Index layout (gitignored, see .gitignore `data/semantic*`):
- `data/semantic.index.npy` — float16 matrix, one L2-normalised row per
  catalog product (rows are unit vectors, so cosine = dot product).
- `data/semantic.meta.json` — `parent_asin` per row (row order), the
  per-bucket IDF vector, vectoriser params, and the catalog SHA256 so a
  stale index built against a different catalog is detected and refused.

Tokens are hashed into a fixed number of buckets with `blake2b` — stable
across processes (unlike Python's salted `hash()`), so a rebuild reproduces
the same index byte-for-byte. TF is sublinear (1+ln tf), IDF is smoothed
per bucket (ln((1+N)/(1+df)) + 1), rows L2-normalised.

Gated behind `NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL` **or**
`feature_flags.enable_semantic_retrieval` in
`neeshops/config/default_strategy.json`. Every failure mode (flag off,
numpy missing, index never built, corrupt files, stale catalog hash) makes
`is_available()` return False / `search()` return [] instead of raising —
`HybridRetriever` then falls back to BM25-only, never to an empty pool.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from neeshops.config.settings import get_settings, load_strategy
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate, Retriever
from neeshops.retrieval.bm25 import _SEARCH_FIELDS, _flatten
from neeshops.utils.logging import log_event
from neeshops.utils.tokens import tokenize

try:  # numpy is the single optional dependency for the semantic path
    import numpy as np
except ImportError:  # pragma: no cover - baseline installs may omit it
    np = None

INDEX_VERSION = 1
MODEL_NAME = "hashed-tfidf-cosine"
DEFAULT_DIM = 1024


def _hash_bucket(token: str, dim: int) -> int:
    """Stable token -> bucket mapping (blake2b, not Python's salted hash)."""
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little") % dim


def _doc_text(row: dict[str, Any]) -> str:
    """Same flattened text as the BM25 index — one field definition."""
    return " ".join(_flatten(row.get(field)) for field in _SEARCH_FIELDS)


def embed_text(text: str, dim: int, idf: "np.ndarray") -> "np.ndarray":
    """Vectorise one piece of text with the hashed TF-IDF scheme, L2-
    normalised so dot product == cosine similarity."""
    vec = np.zeros(dim, dtype=np.float32)
    for token, count in Counter(tokenize(text)).items():
        vec[_hash_bucket(token, dim)] += 1.0 + math.log(count)
    vec *= idf
    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec /= norm
    return vec


def build_index(
    catalog_path: Path,
    index_path: Path,
    meta_path: Path,
    dim: int = DEFAULT_DIM,
) -> dict[str, Any]:
    """Embed every catalog row once and persist the index.

    Called by `scripts/build_semantic_index.py` (and by tests against
    fixture catalogs). Returns stats; raises on a missing catalog.
    """
    if np is None:
        raise RuntimeError("numpy is not installed — pip install numpy")
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog not found at {catalog_path}")

    rows: list[dict[str, Any]] = []
    with open(catalog_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise ValueError(f"Catalog at {catalog_path} is empty")

    start = time.perf_counter()
    n_docs = len(rows)
    bucket_df = np.zeros(dim, dtype=np.int64)
    doc_bucket_counts: list[Counter[int]] = []
    for row in rows:
        buckets = Counter(
            _hash_bucket(token, dim) for token in tokenize(_doc_text(row))
        )
        doc_bucket_counts.append(buckets)
        for bucket in buckets:
            bucket_df[bucket] += 1

    # Smoothed IDF per bucket: present in every doc -> weight ~1, rare -> high.
    idf = np.log((1.0 + n_docs) / (1.0 + bucket_df)).astype(np.float32) + 1.0

    matrix = np.zeros((n_docs, dim), dtype=np.float32)
    for i, buckets in enumerate(doc_bucket_counts):
        for bucket, count in buckets.items():
            matrix[i, bucket] = 1.0 + math.log(count)
    matrix *= idf
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    matrix /= norms

    index_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(index_path, matrix.astype(np.float16))

    sha = hashlib.sha256()
    with open(catalog_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)

    meta = {
        "version": INDEX_VERSION,
        "model": MODEL_NAME,
        "dim": dim,
        "rows": n_docs,
        "catalog_sha256": sha.hexdigest(),
        "tokenizer": "neeshops.utils.tokens.tokenize",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "idf": [round(float(x), 6) for x in idf],
        "parent_asins": [str(row.get("parent_asin", "")) for row in rows],
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f)

    log_event(
        "semantic.index_built",
        path=str(index_path),
        rows=n_docs,
        dim=dim,
        seconds=round(time.perf_counter() - start, 2),
    )
    return {"rows": n_docs, "dim": dim}


class SemanticRetriever(Retriever):
    name = "semantic"

    def __init__(
        self,
        index_path: Optional[Path] = None,
        meta_path: Optional[Path] = None,
        strategy: Optional[dict[str, Any]] = None,
    ) -> None:
        catalog_dir = get_settings().catalog_path.parent
        self.index_path = Path(index_path) if index_path else catalog_dir / "semantic.index.npy"
        self.meta_path = Path(meta_path) if meta_path else catalog_dir / "semantic.meta.json"
        try:
            self._strategy = strategy or load_strategy()
        except Exception:
            self._strategy = {}
        self._matrix: Any = None
        self._idf: Any = None
        self._asins: list[str] = []
        self._dim = DEFAULT_DIM
        self._load_failed = False

    # -- availability ------------------------------------------------------

    def _enabled(self) -> bool:
        if get_settings().enable_semantic_retrieval:
            return True
        return bool(
            self._strategy.get("feature_flags", {}).get(
                "enable_semantic_retrieval", False
            )
        )

    def is_available(self) -> bool:
        """True only when the flag is on, numpy exists, and the index is
        present, parseable, and current. Never raises."""
        try:
            if self._load_failed or not self._enabled() or np is None:
                return False
            if not (self.index_path.exists() and self.meta_path.exists()):
                return False
            if self._matrix is None:
                self._load()
            return self._matrix is not None
        except Exception as exc:
            log_event("semantic.unavailable", reason=f"availability check failed: {exc}")
            self._load_failed = True
            return False

    def _load(self) -> None:
        """Load matrix + meta; any problem flips `_load_failed` so this is
        tried exactly once per process."""
        try:
            with open(self.meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if int(meta.get("version", 0)) != INDEX_VERSION:
                raise ValueError(f"unsupported index version {meta.get('version')!r}")
            matrix = np.load(self.index_path).astype(np.float32)
            idf = np.asarray(meta["idf"], dtype=np.float32)
            asins = [str(a) for a in meta["parent_asins"]]
            if matrix.shape != (len(asins), int(meta.get("dim", DEFAULT_DIM))):
                raise ValueError(
                    f"matrix shape {matrix.shape} disagrees with meta "
                    f"({len(asins)} asins)"
                )
            self._verify_catalog(meta)
            self._matrix = matrix
            self._idf = idf
            self._asins = asins
            self._dim = int(meta.get("dim", DEFAULT_DIM))
        except Exception as exc:
            log_event(
                "semantic.load_failed", path=str(self.index_path), error=str(exc)
            )
            self._matrix = None
            self._load_failed = True

    def _verify_catalog(self, meta: dict[str, Any]) -> None:
        """Refuse an index built against a different catalog (stale index).
        If the catalog file isn't present, the index itself is the source
        of truth and the check passes."""
        if not get_settings().catalog_path.exists():
            return
        sha = hashlib.sha256()
        with open(get_settings().catalog_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha.update(chunk)
        if sha.hexdigest() != meta.get("catalog_sha256"):
            raise ValueError("index was built against a different catalog")

    # -- search ------------------------------------------------------------

    def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
        if not query.strip() or not self.is_available():
            if query.strip():
                log_event("semantic.unavailable", reason="not enabled or index not built")
            return []
        try:
            query_vec = embed_text(query, self._dim, self._idf)
            sims = self._matrix @ query_vec
            return self._top_candidates(sims, top_k)
        except Exception as exc:
            log_event("semantic.search_failed", error=str(exc))
            return []

    def _top_candidates(self, sims: "np.ndarray", top_k: int) -> list[Candidate]:
        """Top-k by cosine, deterministic: score desc, then asin asc."""
        limit = int(top_k) if top_k else len(sims)
        limit = min(max(limit, 0), len(sims))
        if limit == 0:
            return []
        idx = np.argpartition(-sims, limit - 1)[:limit]
        ordered = sorted(
            (int(i) for i in idx),
            key=lambda i: (-float(sims[i]), self._asins[i]),
        )
        return [
            Candidate(parent_asin=self._asins[i], score=float(sims[i]), source=self.name)
            for i in ordered
            if sims[i] > 0.0
        ]
