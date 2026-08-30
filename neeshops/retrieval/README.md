# `neeshops/retrieval/`

**Owner/workstream**: Person 2 — Retrieval & Candidate Generation (see
`docs/neeshops/TEAM_WORKSTREAMS.md`).

## Purpose

Turn a query string + `ConversationState` into a ranked list of candidate
`parent_asin`s from the catalog. Lightweight/in-memory only — no external
vector database (Track 4 requirement 2 / scope).

## Public interfaces

```python
class Retriever(ABC):
    name: str
    def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]: ...
    def is_available(self) -> bool: ...

class Candidate:
    parent_asin: str; score: float; source: str
    metadata: dict | None   # OPTIONAL retrieval provenance — see below

apply_filters(candidates, catalog_lookup, state, filters=None) -> list[Candidate]
merge_weighted(candidate_lists: dict[str, list[Candidate]], weights: dict[str, float]) -> list[Candidate]
merge_rrf(candidate_lists: dict[str, list[Candidate]], weights: dict[str, float], k: int = 60) -> list[Candidate]
stamp_provenance(candidates: list[Candidate], source: str) -> list[Candidate]
```

Implementations: `BM25Retriever`, `SemanticRetriever`, `HybridRetriever`
(the one `neeshops/agent.py` actually calls).

## Current implementation

- `bm25.py`: SQLite FTS5 index built from the catalog's **real** text
  fields — `title`, `categories`, `features`, `details`, `store`,
  `description` (matching the organiser's original weak starter's field
  choice, so BM25 semantics stay comparable to the published baseline).
  Index is built lazily on first `search()` and cached at
  `<catalog>.fts.db` (gitignored); `is_available()` just checks the
  catalog file exists, so a missing catalog degrades to zero candidates
  rather than crashing.
- `semantic.py`: **hashed TF-IDF + numpy cosine** — the lightweight
  baseline from the P2 build order (option "TF-IDF numpy baseline"). The
  only added dependency is `numpy`; no model download, no torch,
  trivially under the <2B-parameter limit.
  - Vectoriser: tokens (same `tokenize()` as BM25's query construction)
    are hashed into a fixed 1024 buckets with `blake2b` (stable across
    processes, so rebuilds are byte-deterministic), sublinear TF
    (1+ln tf), smoothed per-bucket IDF (ln((1+N)/(1+df))+1), rows
    L2-normalised → cosine similarity = dot product.
  - Index built **once** by `scripts/build_semantic_index.py` and
    persisted to `data/semantic.index.npy` (float16 matrix; ~100 MB on
    the 50k catalog, 0.6 MB on the 300-row test catalog) +
    `data/semantic.meta.json` (row→`parent_asin` order, IDF vector,
    vectoriser params, catalog SHA256). Loaded once in
    `SemanticRetriever.__init__`-time lazy load — never rebuilt per turn.
  - A stale index (catalog SHA mismatch), corrupt files, a missing
    numpy, or a disabled flag all make `is_available()` return False /
    `search()` return [] — `HybridRetriever` then falls back to BM25-only,
    never to an empty pool. `is_available()` never raises.
  - Measured latency (300-row test catalog, hybrid with both retrievers):
    **3–4 ms per turn**; the 50k-catalog search is a single 50k×1024
    matvec (~50 MFLOPs) plus an argpartition — projected well under the
    100 ms budget that keeps P3's optional LLM reranker inside MTTC.
  - Gated by `NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL=true` **or**
    `feature_flags.enable_semantic_retrieval: true` in
    `neeshops/config/default_strategy.json`.
  - Swapping in `sentence-transformers/all-MiniLM-L6-v2` later means
    replacing the bodies of `embed_text`/`build_index` only — the
    retriever interface, gating and fail-soft behaviour stay.
- `filters.py`: budget filter against real `price`, category filter
  against real `categories`, and **soft text-containment** filters for
  color/material/brand plus size/style/feature/use_case — the real
  catalog has no discrete fields for these, so a constraint value's text
  is searched across title/categories/features/details/description/store
  instead of exact match. Fails open on sparse metadata (never punishes a
  product for missing data).
- `candidate_merge.py`: `merge_weighted` min-max normalises each
  retriever's raw scores before the weighted sum (BM25 and cosine aren't
  comparable scales), dedups by `parent_asin`, concatenates
  `source` ("bm25+semantic"), and sorts deterministically (exact ties break
  on `parent_asin` ascending). `merge_rrf` is the rank-based alternative
  (reciprocal rank fusion, `retrieval.rrf_k`) for the "fused" strategy —
  no score normalisation needed. Both stamp retrieval provenance into each
  candidate's `metadata` (see the handoff contract below).
- `hybrid.py`: reads `retrieval.strategy`, per-route (`buying`/`browsing`)
  BM25/semantic weights and `candidate_limit` from
  `neeshops/config/default_strategy.json`, calls each available retriever,
  merges, and truncates to `top_k` (agent passes 200 — the pre-rank pool
  that bounds P3's `rerank_limit=40` LLM cost).

## Retrieval provenance — the P3 handoff contract (additive, non-breaking)

The stable contract is unchanged: `Candidate(parent_asin, score, source)`.
Provenance is carried in an OPTIONAL `metadata` dict on the same object —
3A consumes it if present, ignores it if not, and never needs to
reconstruct per-source ordering from the merged score:

```python
candidate.metadata = {
    "rank": 3,                                        # final retrieval rank, 1-based,
                                                      # == position in the returned list
    "bm25":     {"raw_score": 12.34, "rank": 5},      # one entry per source that
    "semantic": {"raw_score": 0.82, "rank": 2},       # actually retrieved this asin
}
```

- `raw_score` is the retriever's own score BEFORE merge normalisation
  (BM25 `bm25()` negated rank; cosine similarity for semantic).
- `rank` inside a source entry is the 1-based position within that
  retriever's own list; the top-level `rank` is the final merged rank.
- Always stamped by `HybridRetriever.search` in every strategy (weighted,
  fused, and single-source via `stamp_provenance`). If `apply_filters`
  drops candidates downstream, the stamped `rank` reflects the pool as
  returned by retrieval, before filtering.
- Diagnostic value: target absent from the pool → recall problem; target
  in the pool (check `raw_score`/`rank` per source) but outside the final
  top-10 → ranking problem.

## Retrieval strategies (`retrieval.strategy` in default_strategy.json)

| Strategy | What P3 gets | Fallback |
|---|---|---|
| `bm25_only` (P2-A) | BM25 list alone, raw BM25 scores | semantic if BM25 unavailable |
| `semantic_only` (P2-B) | semantic list alone, raw cosine scores | BM25 if semantic unavailable |
| `hybrid` (P2-C, default) | current min-max + weighted-sum merge, per-route weights | — |
| `fused` (P2-D) | reciprocal rank fusion (`retrieval.rrf_k`, default 60), per-route weights as multipliers | — |

An unknown value falls back to `hybrid` (logged). Experiments can switch
strategy per run via the safe parameter `retrieval.strategy`
(`neeshops/research/experiment.py`), alongside `retrieval.rrf_k`.
`HybridRetriever` also injects a supplied experiment strategy into BOTH
sub-retrievers (`set_strategy`), so feature-flag changes apply without
reconstructing the semantic index.

## How to extend

Upgrade the semantic encoder by replacing the bodies of `embed_text` /
`build_index` in `semantic.py` (e.g. `sentence-transformers/
all-MiniLM-L6-v2` — 80 MB model, add `sentence-transformers` to
requirements.txt) **without touching `HybridRetriever`** — it already
merges in whatever `SemanticRetriever` returns once `is_available()` is
true. Keep the persisted-artifact contract (`semantic.index.npy` +
`semantic.meta.json`) and bump `INDEX_VERSION` if the meta shape changes.

## Testing without the official catalog

No 50k catalog installed? Generate the deterministic synthetic one:

```bash
python scripts/create_test_catalog.py                # -> data/test_catalog.jsonl (300 rows)
set NEESHOPS_CATALOG_PATH=data/test_catalog.jsonl    # PowerShell: $env:NEESHOPS_CATALOG_PATH="..."
python scripts/setup_catalog.py                      # BM25 FTS5 index
python scripts/build_semantic_index.py               # semantic index
set NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL=true
pytest -q tests/test_retrieval.py tests/test_semantic_retrieval.py tests/test_agent_smoke.py
```

Rebuild both indexes whenever the catalog changes — the semantic loader
verifies the catalog SHA256 and refuses a stale index (fail-soft, BM25
takes over).

## Measuring candidate recall@200 (BM25-only vs hybrid)

For each dev query with a known target ASIN: retrieve `top_k=200` from
`BM25Retriever` alone, then from `HybridRetriever` with semantic enabled,
and check whether the target is in each pool. Compare hit rates to quantify
what the semantic arm adds. A 3-query spot check (e.g. "black canvas
sneaker", "insulated water bottle for hiking", "wireless headphones under
100") is enough for a go/no-go; a full pass over `data/public_set.jsonl`
belongs in the recall report below.

## Known TODOs

- Candidate recall@200 report (hybrid vs BM25-only) on the official 50k
  catalog + 200 public sessions still needs to be produced.
- The official 50k catalog was checksum/row-count validated, indexed, and run
  through the complete 200-session evaluator on 2026-08-28. Overall candidate
  score is recorded in `docs/neeshops/PROJECT_OVERVIEW.md`.
