# Integration Contracts

The actual interfaces between modules, as implemented today — not
aspirational. If you change a signature here, grep for every caller first
(each boundary below lists them) and update this doc in the same PR.

Beginner note: read only the boundary your workstream provides or consumes,
as listed in `docs/neeshops/WORKSTREAM_QUICKSTARTS.md`. Ask P5 before changing
a signature; most tasks should extend behavior behind the existing interface.

---

## Official starter ↔ NeeShops Agent

**Owner**: Person 5 (Integration). **File**: `starter/agent.py`.

| | |
|---|---|
| Input | `Agent(catalog_path: str \| Path = "data/catalog.jsonl", strategy: dict \| None = None)`; then `reset(session_id: str, user_profile: dict)`; then `respond(session_id: str, user_message: str, turn: int, top_k: int)` |
| Output | `{"message": str, "ask_attribute": str \| None, "recommendations": [{"parent_asin": str, "score": float}], "usage": {"prompt_tokens": int, "completion_tokens": int}}` — **matches `docs/agent_api_contract.json` exactly**, `additionalProperties: false` |
| Failure behaviour | Never raises on missing catalog (retrieval degrades to 0 candidates); if `respond()` is called for a `session_id` never `reset()`, `neeshops.conversation.state.StateManager.get()` silently starts a blank session rather than raising (more permissive than the official weak starter, which raised `RuntimeError`) |
| Owner | P5, but the `strategy` kwarg is a **NeeShops-only extension** the official evaluator never passes — P4 relies on it for `scripts/run_experiment.py` |
| Example | `agent = Agent("data/catalog.jsonl"); agent.reset("s1", {"purchase_frequency": "...", "average_prior_rating": 4.0, "rating_style": "...", "preference_tags": [...], "summary": "..."}); agent.respond("s1", "black sneakers under $100", 1, 10)` |

**Do not** add fields to the returned dict — the schema forbids them.
Anything extra (route, per-item `reason`) stays internal to
`neeshops.agent.NeeShopsAgent`'s response and is stripped in
`starter/agent.py` before returning.

---

## Agent ↔ Conversation State

**Owner**: P1 provides, P5 (via `neeshops/agent.py`) consumes.

| | |
|---|---|
| Input | `StateManager.apply_turn(session_id, turn, user_message, extracted_constraints: dict, route: str \| None, asked_attribute: str \| None = None)` |
| Output | `ConversationState` (pydantic model — see `neeshops/models/session.py`): `session_id`, `turn`, `route`, `constraints: dict`, `asked_attributes: list[str]`, `history: list[Turn]`, `user_profile`, `previous_recommendations` |
| Expected types | `extracted_constraints` values are override-only — any field present replaces the prior value outright (Intent Override); `NO_PREFERENCE` (from `neeshops.models.session.NO_PREFERENCE`) is a normal constraint value, not a special case in state storage |
| Failure behaviour | `StateManager.get()` on an unknown `session_id` auto-creates a blank session rather than raising |
| Owner | P1 |
| Example | `state = state_manager.apply_turn("s1", turn=2, user_message="actually black", extracted_constraints={"color": "black"}, route="buying")` → `state.constraint_value("color") == "black"` |

**Do not** append/merge constraint values elsewhere in the codebase —
override semantics live in exactly one place (`StateManager.apply_turn`).

---

## Conversation ↔ Retrieval

**Owner**: P1 provides the query/state, P2 provides the retriever.

| | |
|---|---|
| Input | `Retriever.search(query: str, state: ConversationState, top_k: int)` — `query` is built by `neeshops/agent.py` as `" ".join(keywords(user_message))`, not by `neeshops/conversation/` directly |
| Output | `list[Candidate]` (`neeshops.retrieval.base.Candidate`: `parent_asin`, `score`, `source`) |
| Expected types | `state` may be read but **never mutated** by a retriever |
| Failure behaviour | `Retriever.is_available()` must return `False` rather than raising when the retriever can't run (missing catalog, disabled flag); `HybridRetriever` checks this before calling `search()` |
| Owner | P2 (`HybridRetriever` is the concrete implementation `neeshops/agent.py` uses) |
| Example | `HybridRetriever().search("black sneaker casual", state, top_k=200)` |

---

## Retrieval ↔ Ranking

**Owner**: P2 provides candidates, P3 provides the ranker.

| | |
|---|---|
| Input | `Ranker.rank(candidates: list[Candidate], catalog_lookup: dict[str, dict], state: ConversationState, top_k: int)` |
| Output | `list[Recommendation]` (`neeshops.models.recommendation.Recommendation`: `parent_asin`, `score`, `reason`, `source`), length ≤ `top_k`, ordered best-first |
| Expected types | `catalog_lookup` may be `{}` (catalog not installed) — a ranker must degrade gracefully, not raise |
| Failure behaviour | `reason` must always be a human-readable string, never a fabricated numeric confidence (`docs/neeshops/COMPETITION_NOTES.md`) |
| Owner | P3 |
| Example | see `tests/test_ranking.py` |

---

## Profile ↔ Ranking (personalisation)

**Owner**: P3 (both `neeshops/personalization/` and its only caller,
`neeshops/ranking/heuristic.py`).

| | |
|---|---|
| Input | `personalization_boost(product_row: dict, profile: UserProfile) -> float` |
| Output | float in `[0, 1]` |
| Expected types | `profile.preference_tags` is the only field currently used; empty list → `0.0` |
| Failure behaviour | Never raises; missing product text fields → `0.0` |
| Owner | P3 |
| Contract | This is a **soft** signal — `HeuristicRanker` blends it at
  `ranking.personalization_weight` (default `0.15`) against the retrieval
  score, so an explicit user constraint always dominates (Track 4
  requirement 7; see `tests/test_ranking.py::test_personalization_never_overrides_explicit_low_retrieval_score`) |

---

## Research ↔ Evaluator

**Owner**: P4.

| | |
|---|---|
| Input | `ExperimentRunner(evaluate_fn: (strategy: dict, dataset_path: str) -> dict[str, float])` — `evaluate_fn` is supplied by the caller, not by `neeshops/research/` itself |
| Output | `ExperimentRunner.run(...)` returns a record dict (also appended to `ResultsStore`): `experiment_id`, `name`, `hypothesis`, `parameters`, `metrics`, `baseline_metrics`, `accepted: bool`, `timestamp` |
| Expected types | `evaluate_fn`'s returned dict must contain the key `ExperimentRunner.PRIMARY_METRIC` ("technical_score") — `scripts/run_experiment.py` aliases the real evaluator's `recommended_technical_score` to this key before returning |
| Failure behaviour | `Experiment.__post_init__` raises `ValueError` immediately if any parameter isn't in `SAFE_PARAMETERS` — fails at construction, before any evaluation runs |
| Owner | P4 |
| Example | see `neeshops/research/README.md` |

**`neeshops/research/` never imports `evaluator/` directly** — the
coupling is only in `scripts/run_experiment.py` and `scripts/evaluate.py`,
so P4 can develop/test the research framework without the real catalog.

---

## Blocking-issue check (Part H requirement)

Every boundary above is backed by an actual `abc.ABC` (`Retriever`,
`Ranker`) or a pydantic model (`ConversationState`, `Recommendation`,
`Candidate` as a plain typed class) already in the code — not just a
convention. **No interface stabilisation work is required before parallel
development can start**; this document formalises interfaces that already
exist in working, tested code (see `tests/` for each boundary).
