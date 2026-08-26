# Team workstreams

Five roughly independent streams, each owning its own folder(s), to keep
merge conflicts low. Shared interfaces (below) are the contract between
streams — change them deliberately and flag it to the others, since every
other stream depends on them.

## Workstream 1 — Conversation & Agent Intelligence

**Owns:** `neeshops/conversation/`, `neeshops/agent.py`

**Responsibilities:** conversation state (intent override, no-preference
handling), Buying/Browsing routing, constraint extraction, clarification
policy, top-level orchestration.

**Start here:** `neeshops/conversation/constraints.py` is a small
keyword-based extractor — the highest-leverage place to improve
understanding quality without touching anyone else's module.

## Workstream 2 — Retrieval & Search

**Owns:** `neeshops/retrieval/`

**Responsibilities:** BM25 (working baseline), semantic retrieval
(currently a stub — build the embedding index + ANN search here), metadata
filtering, hybrid weighting, candidate merging.

**Start here:** implement `SemanticRetriever.search()` behind the
`enable_semantic_retrieval` flag — `HybridRetriever` already knows how to
merge it in once it stops raising `NotImplementedError`.

## Workstream 3 — Ranking & Personalisation

**Owns:** `neeshops/ranking/`, `neeshops/personalization/`

**Responsibilities:** reranking quality, human-readable recommendation
reasons, profile-based soft signals, eventually the LLM reranker.

**Start here:** `neeshops/ranking/llm_reranker.py` is an interface stub —
`neeshops/agent.py` currently always uses `HeuristicRanker`; wiring in a
config-driven choice between the two rankers is a good first PR.

## Workstream 4 — Research Agent & Evaluation

**Owns:** `neeshops/research/`, `scripts/evaluate.py`, `scripts/run_experiment.py`

**Responsibilities:** wrapping the (now-vendored) official evaluator,
running experiments, parameter search, metric tracking, public/holdout
comparison, experiment history, deciding what gets accepted into
`neeshops/config/default_strategy.json`.

**Start here:** install the real catalog (`data/README.md`) and confirm
`python scripts/evaluate.py` reproduces the published baseline
(`docs/baseline_results.json`) — everything else in this stream builds on
that reference point.

## Workstream 5 — Integration / Demo / Developer Experience

**Owns:** `frontend/`, `docs/`, integration tests, logging/visualisation

**Responsibilities:** keeping the whole project buildable and testable,
README/architecture upkeep, an optional developer dashboard fed by
`neeshops/utils/logging.py`'s structured events, demo workflow for the
final presentation.

**Start here:** the frontend's Developer views (Runs, Experiments, Media
AI) currently show illustrative sample data — wiring a couple of them to
real `ResultsStore`/log output would make the demo materially stronger.

---

## Shared interfaces (change these carefully)

- `neeshops.retrieval.base.Retriever` / `Candidate` — Workstream 2 owns
  implementations; Workstream 1 (agent.py) and Workstream 3 (ranking)
  consume them.
- `neeshops.ranking.base.Ranker` / `neeshops.models.Recommendation` —
  Workstream 3 owns implementations; Workstream 1 consumes them.
- `neeshops.models.session.ConversationState` — the schema every stream
  reads. Workstream 1 owns mutation logic in `conversation/state.py`.
- `neeshops.config.default_strategy.json` — every retrieval/ranking/
  clarification weight. Workstream 4 (research) is the primary writer once
  experiments start getting accepted; everyone else is a reader.
- `starter/agent.py`'s contract shape — do not change without confirming
  against the organiser's Agent API contract; no workstream should need to
  touch this file at all after Stage 1.

## Branch strategy

```text
main                          protected, always green (tests pass, starter.agent.Agent importable)
dev                           integration branch, PR target

feature/conversation-state    Workstream 1
feature/hybrid-retrieval      Workstream 2
feature/reranker              Workstream 3
feature/research-agent        Workstream 4
feature/developer-demo        Workstream 5
```

PR into `dev`, merge `dev` into `main` once green. Nobody but a
release/integration merge should need to touch `starter/agent.py` — if a
PR does, that's a signal logic is leaking into the adapter and should move
into `neeshops/`.
