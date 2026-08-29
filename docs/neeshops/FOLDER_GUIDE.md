# Folder Guide

This is a reference map. Beginners should first read
`docs/neeshops/BEGINNER_START_HERE.md`, then use their assigned section in
`docs/neeshops/WORKSTREAM_QUICKSTARTS.md`. Return here when you need deeper
module detail.

Grounded in the actual code as of this migration. "Safe to modify?" means
safe for any teammate to touch without cross-workstream coordination —
shared interfaces still need a heads-up in PR description per
`docs/neeshops/INTEGRATION_CONTRACTS.md`.

| Path | Purpose | Owner | Inputs | Outputs | Safe to modify? | How to continue |
|---|---|---|---|---|---|---|
| `starter/agent.py` | Thin contract adapter the evaluator imports | P5 (Integration) | `catalog_path`, `strategy` (optional) | Official `turn_response` dict | **No** — coordinate any change, it's the evaluator's only entry point | Only touch to fix contract conformance; real logic changes belong in `neeshops/` |
| `evaluator/` | Official evaluator, vendored | Nobody (organiser-owned) | `data/catalog.jsonl`, session samples | `results.json`, metrics dict | **Never** | Read it to understand scoring; never edit |
| `neeshops/agent.py` | `NeeShopsAgent` — orchestration only | P5 (Integration), P1 co-owns the state/clarification calls | user message, `session_id`, `turn`, `top_k` | internal response dict (message, ask_attribute, recommendations w/ reason+score, usage, route) | Yes, carefully — it's the seam every workstream's code runs through | Add new pipeline steps here only as calls into other modules, never inline logic |
| `neeshops/conversation/` | State, intent routing, constraint extraction, clarification | **P1** | user message, prior `ConversationState` | updated `ConversationState`, clarification decision | Yes | See `neeshops/conversation/README.md` |
| `neeshops/retrieval/` | BM25 (working), semantic (stub), filters, hybrid merge | **P2** | query string, `ConversationState`, `top_k` | `list[Candidate]` | Yes | See `neeshops/retrieval/README.md` |
| `neeshops/ranking/` | Heuristic reranker (working), LLM reranker (stub) | **P3A** (Ranking Core) | `list[Candidate]`, catalog lookup, state | `list[Recommendation]` | Yes | See `neeshops/ranking/README.md` |
| `neeshops/personalization/` | Soft profile → ranking boost | **P3B** (Personalisation & Evaluation) | catalog row, `UserProfile` | float boost in [0,1] | Yes | Single function, `personalization_boost()` — extend signature only with default-valued kwargs |
| `neeshops/research/` | Experiment/runner/results-store/optimizer | **P4** | strategy dict, dataset path, baseline metrics | accept/reject records in `artifacts/experiments/` | Yes | See `neeshops/research/README.md` |
| `neeshops/models/` | `Product`, `Recommendation`, `ConversationState`, `UserProfile` — pure schema, no behaviour | Shared (P1 owns `session.py`) | — | — | Rarely — it's imported everywhere | Extend fields additively (Optional with defaults); never rename existing fields without a repo-wide search |
| `neeshops/config/` | `default_strategy.json` (every tunable) + `settings.py` (env/.env) | **P4** owns strategy values, everyone reads | env vars, `.env` | `Settings`, strategy dict | Yes for `default_strategy.json` values via experiments; `settings.py` structure rarely | Never hardcode a weight elsewhere — read it from here |
| `neeshops/utils/` | Structured logging, tokenizer, catalog loader | Shared, P5 stewards | — | — | Yes, low-risk | Keep dependency-free (stdlib only) |
| `neeshops/experimental/` | Placeholder for future, **out-of-scope** visual AI ideas | Nobody actively | — | — | Yes, but nothing here may be imported by `neeshops/agent.py` or its dependents | See Part K in `docs/neeshops/TEAM_WORKSTREAMS.md` |
| `data/` | Official catalog/session data + our dev-split tooling output | Organiser-owned data, P4 owns split scripts | GitHub Release download | `dev_split.jsonl`, `holdout_split.jsonl`, `catalog.fts.db` (all gitignored) | `data/README.md` addendum only — never touch `public_set.jsonl` | Install `catalog.jsonl` per `data/README.md`, then `scripts/create_dev_split.py` |
| `scripts/` | Setup/eval/experiment CLIs | **P4** (P5 co-owns `run_baseline.py`) | — | prints, `results.json`, `artifacts/experiments/*.json` | Yes | See per-script docstring; each is <90 lines |
| `tests/` | Official `test_evaluator.py` + our 8 supplementary files | Whoever owns the code under test | — | pass/fail | Yes, additive | Add tests alongside the module you change; `conftest.py` puts repo root on `sys.path` |
| `docs/` (root files) | Official competition docs | Nobody (organiser-owned) | — | — | **Never** | Read-only reference |
| `docs/neeshops/` | Our docs (this file included) | **P5** stewards, everyone edits their own section | — | — | Yes | Keep filenames distinct from official `docs/*.md` to avoid collisions |
| `frontend/` | Static clickable demo prototype, decoupled from the Agent | **P5**, optional, low priority | — | static HTML | Yes | Not a competition-scored workstream — see Part J |
| `artifacts/` | Gitignored experiment output | — | `scripts/evaluate.py`, `scripts/run_experiment.py` | — | N/A (generated) | Never commit; if it must be shared, curate into `docs/neeshops/EXPERIMENTS.md` |

## Per-module detail

### `neeshops/conversation/`

- **Problem it solves**: turning free text + prior state into structured
  constraints, a Buying/Browsing route, and a clarification decision.
- **Interfaces exposed**: `StateManager.reset/get/apply_turn/
  record_recommendations/mark_no_preference`; `extract_constraints(message)
  -> dict`; `detect_route(message, previous_route, constraint_count) ->
  str`; `ClarificationEngine.decide(state, candidates, turn) -> dict`.
- **Called by**: `neeshops/agent.py` only.
- **Currently capable of**: intent-override (new value replaces old),
  no-preference storage and never re-asking, sticky Buying/Browsing
  routing, keyword-based constraint extraction (color, budget, no-preference
  phrases), a rule-based ask-vs-recommend decision with a question budget.
- **TODO**: constraint extraction covers only `color`/`budget`/no-preference
  today — `material`, `size`, `style`, `brand`, `feature`, `use_case` are
  declared in `CONSTRAINT_FIELDS` but nothing populates them from text yet.
  This is P1's highest-leverage next task.
- **How to add functionality safely**: extend `extract_constraints()` with
  more field patterns: it returns only fields a message actually speaks
  to, and `StateManager.apply_turn` already applies override semantics —
  no other module needs to change.
- **Tests to run after changing it**: `tests/test_state.py`,
  `tests/test_intent_override.py`, then `tests/test_agent_smoke.py` and
  `tests/test_agent_contract.py` to confirm the whole pipeline still runs.

### `neeshops/retrieval/`

- **Problem it solves**: turning a query + state into ranked candidate
  `parent_asin`s from the catalog.
- **Interfaces exposed**: `Retriever.search(query, state, top_k) ->
  list[Candidate]` (ABC — `BM25Retriever`, `SemanticRetriever`,
  `HybridRetriever` all implement it); `apply_filters(candidates,
  catalog_lookup, state, filters=None) -> list[Candidate]`;
  `merge_weighted(candidate_lists, weights) -> list[Candidate]`.
- **Called by**: `neeshops/agent.py` (via `HybridRetriever`, injected as
  `retriever`); `scripts/setup_catalog.py` (builds the BM25 index
  directly).
- **Currently capable of**: BM25 over a SQLite FTS5 index built from the
  real catalog fields (`title`, `categories`, `features`, `details`,
  `store`, `description`); soft text-containment filters for
  color/material/brand (the real catalog has no discrete fields for
  these — see the module docstring in `filters.py`); budget filtering
  against real `price`; category filtering against real `categories`;
  weighted merge of multiple retrievers with per-route config weights.
- **TODO**: `SemanticRetriever.search()` raises `NotImplementedError` —
  it's a clean interface stub behind `NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL`
  (default off). This is P2's primary deliverable.
- **How to add functionality safely**: implement `SemanticRetriever`
  without touching `HybridRetriever` — it already calls
  `semantic.is_available()` and merges in whatever it returns.
- **Tests to run after changing it**: `tests/test_retrieval.py` (uses a
  small fixture catalog, no real data needed), then
  `tests/test_agent_smoke.py`.
- **Do not modify**: `evaluator/`, or the field names in
  `neeshops/models/product.py` without checking `bm25.py`'s
  `_SEARCH_FIELDS` and `filters.py`'s `_TEXT_FIELDS` stay consistent.

### `neeshops/ranking/`

- **Problem it solves**: ordering candidates and attaching a
  human-readable reason.
- **Interfaces exposed**: `Ranker.rank(candidates, catalog_lookup, state,
  top_k) -> list[Recommendation]` (ABC — `HeuristicRanker`,
  `LLMReranker`).
- **Called by**: `neeshops/agent.py` only, when the clarification engine
  says `should_recommend`.
- **Currently capable of** (`HeuristicRanker`): blends the retrieval score
  with `personalization_boost()`, reranks the top
  `ranking.rerank_limit` candidates (config), attaches one of three
  human-readable reasons by rank position. **No numeric confidence is
  fabricated** — see `docs/neeshops/COMPETITION_NOTES.md`.
- **TODO**: `LLMReranker.rank()` raises `NotImplementedError` — interface
  stub behind `NEESHOPS_ENABLE_LLM_RERANKER` (default off). This is P3's
  primary deliverable, with a hard requirement: bounded candidate count
  into the LLM, tracked token usage, and a working fallback to
  `HeuristicRanker` when disabled/unavailable.
- **How to add functionality safely**: `neeshops/agent.py` currently
  always constructs `HeuristicRanker` — wiring a config-driven choice
  between rankers (falling back cleanly when `LLMReranker.is_available()`
  is false) is the safe integration point; don't hardcode a ranker choice
  inside `HeuristicRanker` or `LLMReranker` themselves.
- **Tests to run after changing it**: `tests/test_ranking.py` (covers
  ordering, `top_k`, and that personalization stays a soft boost — Track 4
  requirement 7), then `tests/test_agent_smoke.py`.

### `neeshops/research/`

- **Problem it solves**: controlled, evaluator-backed experimentation over
  a declared-safe parameter allowlist — never a code change.
- **Interfaces exposed**: `Experiment(name, hypothesis, parameters)` (only
  accepts dot-paths in `SAFE_PARAMETERS`); `ExperimentRunner(evaluate_fn,
  results_store).run(experiment, dataset_path, baseline_metrics) ->
  record`; `ResultsStore.record/all/accepted`; `propose_grid`/
  `propose_random`/`next_experiments`.
- **Called by**: `scripts/run_experiment.py` wires `evaluate_fn` to the
  real `evaluator.local_evaluator.evaluate()`.
- **Currently capable of**: building a full strategy dict from a base +
  parameter overrides, running it through a supplied evaluator function,
  accept/reject on a primary metric threshold, append-only JSONL history
  under `artifacts/experiments/` (gitignored).
- **TODO**: `optimizer.next_experiments()` is a random-search placeholder
  — it doesn't yet look at `scenario_metrics` to target the weakest
  scenario. No experiment has actually been run yet (catalog not
  installed in this environment) — `docs/neeshops/EXPERIMENTS.md` is
  currently empty by design, not by oversight.
- **How to add functionality safely**: extend `SAFE_PARAMETERS`
  deliberately when a new tunable is added to
  `neeshops/config/default_strategy.json`; never let an experiment write
  to `evaluator/`.
- **Tests to run after changing it**: `tests/test_research.py` (safe-
  parameter enforcement, strategy building, accept/reject wiring).
- **Do not modify**: `evaluator/local_evaluator.py` under any circumstance,
  including "just for a faster experiment loop."
