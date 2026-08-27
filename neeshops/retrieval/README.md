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

apply_filters(candidates, catalog_lookup, state, filters=None) -> list[Candidate]
merge_weighted(candidate_lists: dict[str, list[Candidate]], weights: dict[str, float]) -> list[Candidate]
```

Implementations: `BM25Retriever`, `SemanticRetriever` (stub),
`HybridRetriever` (the one `neeshops/agent.py` actually calls).

## Current implementation

- `bm25.py`: SQLite FTS5 index built from the catalog's **real** text
  fields — `title`, `categories`, `features`, `details`, `store`,
  `description` (matching the organiser's original weak starter's field
  choice, so BM25 semantics stay comparable to the published baseline).
  Index is built lazily on first `search()` and cached at
  `<catalog>.fts.db` (gitignored); `is_available()` just checks the
  catalog file exists, so a missing catalog degrades to zero candidates
  rather than crashing.
- `semantic.py`: interface stub. `search()` raises `NotImplementedError`
  when called directly, but `is_available()` returns `False` unless
  `NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL=true` **and** an index is actually
  built — `HybridRetriever` checks `is_available()` first, so the stub is
  safe to leave disabled.
- `filters.py`: budget filter against real `price`, category filter
  against real `categories`, and **soft text-containment** filters for
  color/material/brand — the real catalog has no discrete fields for
  these, so a constraint value's text is searched across
  title/categories/features/details/description/store instead of exact
  match. Fails open on sparse metadata (never punishes a product for
  missing data).
- `hybrid.py`: reads per-route (`buying`/`browsing`) BM25/semantic weights
  from `neeshops/config/default_strategy.json`, calls each available
  retriever, merges via `candidate_merge.merge_weighted` (min-max
  normalises each retriever's raw scores before combining — BM25 and
  cosine-similarity scores aren't comparable scales).

## How to extend

Implement `SemanticRetriever.search()` (embed `query`, ANN search against
an in-memory index — e.g. a plain numpy matrix + cosine similarity is
enough; **do not** stand up an external vector DB) without touching
`HybridRetriever` — it already merges in whatever `SemanticRetriever`
returns once `is_available()` is true.

## How to test

```bash
pytest tests/test_retrieval.py tests/test_agent_smoke.py
```
`test_retrieval.py` uses a small in-memory fixture catalog — no real
50k-product catalog required to develop against.

## Known TODOs

- Semantic retrieval unimplemented (primary P2 deliverable).
- Retrieval has never been measured against the real 50k catalog in this
  environment (catalog not installed) — only against fixture data and a
  mechanical evaluator smoke test.
- Metadata filters for `size`/`style`/`feature`/`use_case` don't exist
  yet — extend `DEFAULT_FILTERS` in `filters.py`.
