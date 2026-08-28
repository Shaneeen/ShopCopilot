# Team Workstreams

Five people, minimised merge conflicts, full coverage of the scored
challenge. No one's primary responsibility is UI (Track 4 is a
backend/headless challenge — see `docs/neeshops/TRACK4_REQUIREMENTS.md`).

Balance is by technical effort and integration responsibility, not file
count — P5 owns fewer files but carries cross-cutting integration risk;
P2/P3 carry the heaviest new-implementation load (semantic retrieval, LLM
reranking) since those are the two biggest unimplemented stubs in the
current codebase.

---

## Person 1 — Conversation Intelligence & State

### Owned folders
`neeshops/conversation/` (+ read/extend the calls into it from
`neeshops/agent.py`).

### Allowed/shared interfaces
Provides: `StateManager`, `extract_constraints`, `detect_route`,
`ClarificationEngine.decide` (see `docs/neeshops/INTEGRATION_CONTRACTS.md`
→ "Agent ↔ Conversation State", "Conversation ↔ Retrieval"). Consumes:
`neeshops.models.session.ConversationState` schema (shared — coordinate
schema changes with everyone).

### Files to avoid modifying
`neeshops/retrieval/`, `neeshops/ranking/`, `starter/agent.py`,
`evaluator/`.

### Responsibilities
Conversation state, Buying/Browsing interpretation, information
accumulation, Intent Override, Boundary/no-preference behaviour,
clarification selection, state transitions, question history, structured
constraints.

### Deliverables

- **P1-D1** — Persistent per-session state surviving multiple `respond()`
  calls, isolated by `session_id`.
  *Acceptance*: `tests/test_state.py` passes (already does — extend it as
  you add fields).
- **P1-D2** — Intent Override correctly replaces an obsolete value.
  *Acceptance*: `blue → "actually black" → active color = black`;
  `tests/test_intent_override.py` (already passes — the baseline case is
  covered; extend for the fields you newly extract).
- **P1-D3** — Boundary behaviour never re-asks a `NO_PREFERENCE` field.
  *Acceptance*: `tests/test_intent_override.py::test_no_preference_is_recorded_and_not_reasked`
  (already passes).
- **P1-D4** — Buying/Browsing routing produces a structured route usable
  by retrieval.
  *Acceptance*: `detect_route()` unit-tested for all four scenario
  archetypes (buying, browsing, intent_override, boundary phrasing) — not
  yet written; add to `tests/test_state.py` or a new
  `tests/test_intent_routing.py`.
- **P1-D5** — Clarification engine only ever emits a valid official
  `ask_attribute` (`category`, `material`, `color`, `size`, `style`,
  `brand`, `budget`, `feature`, `use_case`, `other`, or `null`).
  *Acceptance*: add an explicit assertion test — `CONSTRAINT_FIELDS`
  currently excludes `other`, confirm nothing ever emits an out-of-enum
  value.
- **P1-D6** — Tests covering all four scenario types exist and pass.

### Success metrics
Functional correctness first (tests). Then, once P4's evaluator wiring is
usable: per-scenario Hit Rate@10/MRR delta on Buying/Browsing/Intent
Override/Boundary specifically — **never claim improvement without an
actual evaluator run**.

### Merge checklist
- [ ] `pytest tests/test_state.py tests/test_intent_override.py tests/test_agent_smoke.py tests/test_agent_contract.py` passes
- [ ] No change to `StateManager.apply_turn`'s override semantics without flagging it in the PR
- [ ] `docs/neeshops/INTEGRATION_CONTRACTS.md` updated if a signature changed

### Definition of Done
All 6 deliverables have passing tests; `neeshops/conversation/README.md`
reflects the actual extraction coverage (not aspirational).

### First action
Extend `extract_constraints()` in `neeshops/conversation/constraints.py`
to populate `material`, `size`, `style`, `brand` (currently only
`color`/`budget`/no-preference are extracted) — highest-leverage,
self-contained, no other module needs to change.

---

## Person 2 — Retrieval & Candidate Generation

### Owned folders
`neeshops/retrieval/`.

### Allowed/shared interfaces
Provides: `Retriever` (ABC), `HybridRetriever`, `apply_filters`,
`merge_weighted` (see `docs/neeshops/INTEGRATION_CONTRACTS.md` →
"Conversation ↔ Retrieval", "Retrieval ↔ Ranking"). Consumes:
`ConversationState` (read-only), `neeshops/config/default_strategy.json`'s
`retrieval` section.

### Files to avoid modifying
`neeshops/conversation/`, `neeshops/ranking/`, `starter/agent.py`,
`evaluator/`.

### Responsibilities
Official-schema BM25 (already working), keyword retrieval, semantic
retrieval, metadata filtering, query representation, hybrid retrieval,
candidate merging, configurable retrieval weights, candidate truncation.

### Deliverables

- **P2-D1** — Official BM25 path works through NeeShops without breaking
  baseline compatibility.
  *Acceptance*: `neeshops/retrieval/bm25.py` indexes the same fields
  (`title`, `categories`, `features`, `details`, `store`, `description`)
  the organiser's original weak starter used — **already done**; verify
  it stays true after any change with `tests/test_retrieval.py`.
- **P2-D2** — Retrievers share a stable interface.
  *Acceptance*: `Retriever` ABC — **already done**, `BM25Retriever`,
  `SemanticRetriever`, `HybridRetriever` all implement it.
- **P2-D3** — Semantic/dense retrieval implemented, lightweight/in-memory
  (e.g. a plain numpy matrix + cosine similarity, or a small local ANN
  library — never an external vector database service).
  *Acceptance*: `SemanticRetriever.search()` no longer raises
  `NotImplementedError` when `NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL=true`;
  add `tests/test_semantic_retrieval.py`.
- **P2-D4** — Hybrid retrieval merges keyword + semantic candidates
  reproducibly.
  *Acceptance*: `merge_weighted()` — **already done and tested**; extend
  coverage once semantic retrieval is real.
- **P2-D5** — Metadata filters support category, budget/price,
  brand/store, material, color, size/style where inferable.
  *Acceptance*: `filters.py` — budget and category done against real
  fields; material/color/brand are soft text-containment (documented
  limitation, real catalog has no discrete fields); size/style not yet
  attempted — extend `DEFAULT_FILTERS`.
- **P2-D6** — Buying/Browsing retrieval weights configurable, not
  hardcoded in multiple files.
  *Acceptance*: **already done** — `neeshops/config/default_strategy.json`
  → `retrieval.buying`/`retrieval.browsing`, read once in
  `HybridRetriever.weights_for_route()`.

### Success metrics
Candidate recall (does the target ASIN ever appear in the pre-ranking
candidate pool?), Hit Rate@10 after ranking integration, retrieval
latency, scenario-level Buying/Browsing performance — all **measured via
the real evaluator once the catalog is installed**, never estimated.

### Merge checklist
- [ ] `pytest tests/test_retrieval.py tests/test_agent_smoke.py` passes
- [ ] New retriever implements `is_available()` correctly (never raises)
- [ ] No hardcoded weight outside `default_strategy.json`

### Definition of Done
`SemanticRetriever` functional and covered by tests; `HybridRetriever`
merges both paths correctly; `neeshops/retrieval/README.md` updated.

### First action
Install the real catalog locally (`data/README.md`) and run
`python scripts/setup_catalog.py` to confirm the BM25 index actually
builds cleanly against all 50,000 real rows (only ever tested against a
3-row fixture in this environment so far) — then start on
`SemanticRetriever`.

---

## Person 3 — Ranking, Query Intelligence & Personalisation

### Owned folders
`neeshops/ranking/`, `neeshops/personalization/`.

### Allowed/shared interfaces
Provides: `Ranker` (ABC), `HeuristicRanker`, `personalization_boost` (see
`docs/neeshops/INTEGRATION_CONTRACTS.md` → "Retrieval ↔ Ranking", "Profile
↔ Ranking"). Consumes: `list[Candidate]` from P2, `ConversationState.user_profile`.

### Files to avoid modifying
`neeshops/retrieval/`, `neeshops/conversation/`, `starter/agent.py`,
`evaluator/`.

### Responsibilities
Candidate reranking, semantic ranking, optional LLM reranking, query
rewriting where appropriate, soft user-profile signals, ranking
explanation strings, ranking latency/token cost, fallback ranking when an
external model is unavailable.

### Deliverables

- **P3-D1** — Deterministic baseline reranker exists.
  *Acceptance*: `HeuristicRanker` — **already done and tested**
  (`tests/test_ranking.py`).
- **P3-D2** — Personalisation converts the official aggregate profile into
  **soft** ranking features; explicit constraints take priority.
  *Acceptance*: `personalization_boost()` + `ranking.personalization_weight`
  (default 0.15) — **already done**; verified by
  `tests/test_ranking.py::test_personalization_never_overrides_explicit_low_retrieval_score`.
- **P3-D3** — If an LLM reranker is used: bounded candidate count in,
  token usage tracked, secrets from environment variables only, and a
  working fallback when unavailable.
  *Acceptance*: `LLMReranker` currently raises `NotImplementedError` when
  disabled — implement it AND wire the fallback into
  `neeshops/agent.py` (currently always constructs `HeuristicRanker`
  unconditionally; this is the actual integration gap).
- **P3-D4** — Ranker output is a valid, ordered `parent_asin` list.
  *Acceptance*: **already done** for `HeuristicRanker`.
- **P3-D5** — Compare ranking strategy against retrieval-only output.
  *Acceptance*: a script or experiment (coordinate with P4) that runs the
  evaluator with `HeuristicRanker` vs. an identity ranker (pass-through
  retrieval order) and reports the MRR delta.

### Success metrics
MRR, Top-10 ordering quality, latency, token usage/cost if an LLM is used
— all measured, never estimated. Report actual deltas against
retrieval-only ordering.

### Merge checklist
- [ ] `pytest tests/test_ranking.py tests/test_agent_smoke.py` passes
- [ ] No numeric confidence fabricated in `reason` strings
- [ ] LLM path (if implemented) has a tested fallback

### Definition of Done
`LLMReranker` functional and gated correctly, `neeshops/agent.py` chooses
between rankers based on availability rather than hardcoding
`HeuristicRanker`, `neeshops/ranking/README.md` updated.

### First action
Wire a config-driven ranker choice into `neeshops/agent.py`
(`NeeShopsAgent.__init__` currently hardcodes `ranker or
HeuristicRanker(...)`) so P3 has a real integration point to build
`LLMReranker` toward, before writing any LLM prompt code.

---

## Person 4 — Research Agent, Evaluation & Experimentation

### Owned folders
`neeshops/research/`, `scripts/evaluate.py`, `scripts/run_experiment.py`,
`scripts/create_dev_split.py`.

### Allowed/shared interfaces
Provides: `Experiment`, `ExperimentRunner`, `ResultsStore`, `optimizer`
functions (see `docs/neeshops/INTEGRATION_CONTRACTS.md` → "Research ↔
Evaluator"). Consumes: `evaluator.local_evaluator.evaluate/catalog_index/
load_jsonl` (official, read-only) via `starter.agent.Agent`.

### Files to avoid modifying
`evaluator/` (**never**), `neeshops/conversation/`, `neeshops/retrieval/`,
`neeshops/ranking/` (P4 *runs* experiments over their config values, never
edits their code).

### Responsibilities
Official evaluator integration/wrapping, development/holdout split,
experiment framework, configuration comparison, metric reporting,
scenario-level analysis, controlled optimisation, experiment logs. The
research framework must never blindly rewrite production code — it only
ever proposes different values for parameters already declared safe in
`neeshops.research.experiment.SAFE_PARAMETERS`.

### Deliverables

- **P4-D1** — Reproduce the official weak baseline (`Hit Rate@10 0.125`,
  `MRR 0.068034`, `MTTC 9.81`, `TechnicalScore 0.10671`) on the real
  public set.
  *Acceptance*: `python scripts/evaluate.py` output matches
  `docs/baseline_results.json` within reasonable numerical tolerance.
  **Not yet done in this environment — the real catalog isn't installed.
  This is the actual first milestone (M1).**
- **P4-D2** — Deterministic internal dev/holdout split.
  *Acceptance*: `scripts/create_dev_split.py` — **already implemented**,
  not yet run against the real 200-session set here.
- **P4-D3** — Experiment result schema records experiment ID, hypothesis,
  configuration, Hit Rate@10, MRR, MTTC, Efficiency, TechnicalScore,
  per-scenario metrics, token use, latency, accepted/rejected.
  *Acceptance*: `ResultsStore.record()` — **already captures** `metrics`
  (whatever `evaluate_fn` returns, which is the full official `evaluate()`
  dict including `scenario_metrics` and `reported_token_usage`),
  `baseline_metrics`, `accepted`, `timestamp`. Latency per-session isn't
  captured yet — extend if needed.
- **P4-D4** — Run controlled A/B experiments.
  *Acceptance*: `scripts/run_experiment.py --grid ...` /
  `--random N` — **already implemented**, needs a real catalog to
  actually execute meaningfully.
- **P4-D5** — Research optimisation proposes/selects safe configuration
  changes without modifying the evaluator.
  *Acceptance*: `propose_grid`/`propose_random` — done;
  `next_experiments()` targeting weak scenarios specifically — not done
  (currently falls back to `propose_random(n=3)`).
- **P4-D6** — Readable evaluation summary.
  *Acceptance*: `docs/neeshops/EXPERIMENTS.md` populated with real,
  measured results once experiments actually run (currently empty by
  design).

### Success metrics
Primary: `TechnicalScore` (`recommended_technical_score` in the evaluator
output). Secondary: scenario metrics, dev/holdout generalisation gap,
reproducibility, token/cost efficiency.

### Merge checklist
- [ ] `pytest tests/test_research.py` passes
- [ ] `evaluator/local_evaluator.py` diff against `upstream/main` is empty (never modified)
- [ ] New `SAFE_PARAMETERS` entries added deliberately, not silently

### Definition of Done
Baseline reproduced and recorded with real numbers; at least one real
experiment cycle (propose → run → accept/reject) recorded in
`docs/neeshops/EXPERIMENTS.md` with actual evaluator output.

### First action
Install the real catalog (`data/README.md`) and run
`python scripts/evaluate.py` to get the **first real baseline
reproduction** — this unblocks every other workstream's "measure the
actual delta" requirement.

---

## Person 5 — Agent Integration, Reliability & Competition Delivery

Not primarily frontend development.

### Owned folders
`neeshops/agent.py`, `starter/agent.py`, integration tests
(`tests/test_agent_contract.py`, `tests/test_agent_smoke.py`),
`neeshops/config/`, `neeshops/utils/`, root `README.md`, demo tooling.

### Allowed/shared interfaces
Owns the seam every other workstream's code runs through
(`neeshops/agent.py`'s call sequence) and the evaluator-facing contract
(`starter/agent.py`). See `docs/neeshops/INTEGRATION_CONTRACTS.md` in
full — P5 is responsible for keeping the whole document accurate.

### Files to avoid modifying
Don't reimplement P1–P4's logic inside `neeshops/agent.py` — only call
into their modules. Never modify `evaluator/`.

### Responsibilities
Official `starter.agent.Agent` compatibility, orchestration integration,
response validation, error/fallback behaviour, token reporting, latency
measurement, logging, integration tests, competition reproducibility,
README quality, end-to-end demo path, an optional minimal developer
visualisation (only if core engineering is ahead of schedule — see Part J
below).

### Deliverables

- **P5-D1** — `starter.agent.Agent` passes official contract expectations.
  *Acceptance*: `tests/test_agent_contract.py` — **already passes**;
  response shape verified byte-for-byte against
  `docs/agent_api_contract.json` (see audit evidence in
  `docs/neeshops/PROJECT_OVERVIEW.md`).
- **P5-D2** — One complete session runs end-to-end (reset → respond →
  state → retrieval → ranking → valid response) without manual
  intervention.
  *Acceptance*: `tests/test_agent_smoke.py` — **already passes**; and a
  full 10-turn session was run through the real
  `evaluator.local_evaluator.evaluate()` against a schema-accurate fixture
  catalog with zero exceptions (see `docs/neeshops/PROJECT_OVERVIEW.md`
  evidence log).
- **P5-D3** — Failures in optional components have sensible fallbacks
  (e.g. LLM unavailable → deterministic retrieval/ranking still returns a
  valid response).
  *Acceptance*: **not yet built** — depends on P3's LLM fallback wiring
  (P3-D3) landing in `neeshops/agent.py`; P5 reviews/merges that PR.
- **P5-D4** — Integration test covers all four scenario families (Buying,
  Browsing, Intent Override, Boundary).
  *Acceptance*: **partially done** — `tests/test_agent_smoke.py` runs a
  generic multi-turn conversation; add one test per scenario archetype.
- **P5-D5** — Project setup reproducible from README by another teammate.
  *Acceptance*: root `README.md`'s NeeShops section — already documents
  setup/test/eval commands; verify a clean-checkout teammate can follow it
  without asking questions.
- **P5-D6 — Agent Trace Viewer.** Demo flow: multi-turn Agent session,
  internal decisions/logs, results, evaluator metrics — made *visible*,
  not just logged.
  *What it is*: run a real session through `starter.agent.Agent`, capture
  the structured JSON-line events `neeshops/utils/logging.py` already
  emits per stage (`state.reset`, `state.apply_turn`, `retrieval.hybrid`,
  `agent.respond`, ...), and render them as a readable per-turn trace —
  intent detected, constraints extracted, retrieval route + candidate
  counts, clarification decision, final ranked recommendations with their
  `reason`. This is the frontend's existing "Agent Run Inspector" mockup
  (`frontend/Main.dc.html`, currently sample data only) wired to a real
  session instead of fake data.
  *Why it's worth doing*: it's read-only tooling over logs that already
  exist — **zero risk to the scored Agent/evaluator path** — and it
  directly answers "prove this isn't a black box," which is genuine
  Innovation/Impact material and exactly what the demo video can show per
  the official deliverables ("API interaction, evaluator, inference
  results, developer dashboard, metrics, Agent trace" — no shopping
  frontend required).
  *Acceptance*: a script (e.g. `scripts/generate_trace_report.py`) that
  runs a session and produces either a readable console trace or a static
  HTML report reusing the frontend's visual design; committed and runnable
  by any teammate; referenced from the README as part of the demo
  instructions.
  *Not required for*: M0–M6. This is a submission-polish item for M7 —
  build it once core engineering is stable, not before.
- **P5-D7** — Documentation records final team contributions.
  *Acceptance*: add a "Team Contributions" section to root `README.md`
  before submission.

### Success metrics
No broken official contract, evaluator completes, reproducible setup, no
committed secrets, acceptable runtime/latency, reliable final demo.

### Merge checklist
- [ ] `pytest` (full suite) passes
- [ ] `python -c "from starter.agent import Agent"` succeeds
- [ ] `git diff upstream/main -- evaluator/` is empty
- [ ] No `.env`, API key, or token committed

### Definition of Done
All P5 deliverables acceptance-checked; `docs/neeshops/INTEGRATION_CONTRACTS.md`
and `docs/neeshops/PROJECT_OVERVIEW.md` current; demo trace script exists
and runs.

### First action
Wire the LLM-reranker fallback integration point into `neeshops/agent.py`
(the same change P3's first action depends on) — this single change
unblocks both P3-D3 and P5-D3 and should be done jointly/reviewed
together to avoid two people redesigning the same seam independently.

---

# Dependency Map

| Workstream | Depends on | Provides to |
|---|---|---|
| P1 Conversation | `neeshops.models.session` schema (shared) | P2 (route + state), P3 (state for personalisation context), P5 (orchestration calls) |
| P2 Retrieval | Product catalog (`data/catalog.jsonl`), P1's `ConversationState` | P3 (candidates) |
| P3 Ranking | P2's candidates, P1's state/profile | P5 (final recommendations) |
| P4 Research | A working Agent + the official evaluator | Entire team (measured deltas, accepted config changes to `default_strategy.json`) |
| P5 Integration | All four other workstreams' interfaces | Final system, competition submission |

## Integration checkpoints

1. **After P1's constraint-extraction extension** — P2 should re-verify
   `apply_filters()` still behaves correctly with the newly-populated
   `material`/`size`/`style`/`brand` fields.
2. **After P2's semantic retriever lands** — P3 re-verifies
   `HeuristicRanker` still handles a mixed `bm25+semantic` `source` string
   correctly (it already does — `candidate_merge.py` concatenates sources
   with `+`).
3. **After P3's LLM-reranker fallback wiring** — P5 merges it into
   `neeshops/agent.py` and re-runs the full integration test suite.
4. **After each P4 experiment cycle** — any accepted config change to
   `default_strategy.json` should be flagged to P1/P2/P3 since it changes
   their modules' runtime behaviour without a code change.

---

# Team Milestones

## M0 — Backbone Ready
- [x] Official evaluator preserved, byte-identical to upstream
- [x] Official `starter.agent.Agent` import works
- [x] Tests execute (28/28 passing as of this audit)
- [x] Folder ownership documented (this file + `docs/neeshops/FOLDER_GUIDE.md`)
- [x] Five developers can branch independently (module boundaries + interfaces documented)

**Status: complete** — see `docs/neeshops/PROJECT_OVERVIEW.md` for the
verdict and evidence.

## M1 — Baseline Reproduced
- [ ] Official catalog installed (`data/catalog.jsonl`, 50k rows)
- [ ] `python3 -m evaluator.local_evaluator` runs to completion on the
      real public set
- [ ] Baseline reproduced within reasonable numerical tolerance of
      `docs/baseline_results.json`
- [ ] Results recorded in `docs/neeshops/PROJECT_OVERVIEW.md`

Owner: P4. **Blocking for every other milestone's "measured" claims.**

## M2 — Stateful Agent
- [ ] Conversation state functional across all four scenario types
- [ ] No invalid API responses (schema-conformant on every turn)

Owner: P1, reviewed by P5.

## M3 — Hybrid Retrieval
- [ ] BM25 + semantic/metadata path functional
- [ ] Evaluator completes with semantic retrieval enabled
- [ ] Results compared against M1 baseline

Owner: P2.

## M4 — Ranking & Personalisation
- [ ] Reranking integrated (heuristic and/or LLM with fallback)
- [ ] Personalisation integrated
- [ ] MRR and overall TechnicalScore measured against M3

Owner: P3.

## M5 — Research/Evaluation Loop
- [ ] Controlled experiments run against real data
- [ ] Configuration comparisons recorded
- [ ] Accepted/rejected experiments reproducible from
      `artifacts/experiments/` + `docs/neeshops/EXPERIMENTS.md`

Owner: P4.

## M6 — Integrated Candidate
- [ ] All five workstreams merged to `main`
- [ ] Official evaluator passes end-to-end
- [ ] Full test suite passes
- [ ] Holdout split results recorded (generalisation check)
- [ ] No secrets committed

Owner: P5.

## M7 — Submission Ready
- [ ] README complete (setup, reproduction, limitations, future work,
      contributions)
- [ ] Written project description supported by evidence in this repo
- [ ] Architecture documented (`docs/neeshops/ARCHITECTURE.md`,
      `PROJECT_OVERVIEW.md`)
- [ ] Demo recorded/rehearsed (trace + evaluator metrics, per P5-D6)
- [ ] Limitations recorded
- [ ] Team contributions recorded

Owner: P5, with input from all.

No calendar dates are set here — the repository has no prior scheduling
information to draw from; the team should timebox these against the
actual submission deadline.

---

# Branch / Collaboration Plan

```text
main                                  protected; official evaluator import + full test suite must pass
backup/pre-official-migration         historical snapshot, do not build on this

feature/conversation-intelligence     P1
feature/hybrid-retrieval              P2
feature/ranking-personalization       P3
feature/research-evaluation           P4
feature/agent-integration             P5
```

- No long-lived direct edits to `main` — branch, PR, merge.
- `starter/agent.py` changes are tightly controlled — P5 reviews every
  change to it regardless of who authors it, since it's the evaluator's
  only entry point.
- Avoid two people simultaneously redesigning a shared interface
  (`Retriever`, `Ranker`, `ConversationState`) — flag intended interface
  changes in the PR description and check
  `docs/neeshops/INTEGRATION_CONTRACTS.md` first.
- Require `pytest` green before merge (CI or manual — no CI config exists
  in this repo yet; P5 may add one as a stretch goal, not required for
  M0–M6).
- Document every interface change in
  `docs/neeshops/INTEGRATION_CONTRACTS.md` in the same PR.

## Remotes

```text
origin      → https://github.com/Shaneeen/ShopCopilot.git (team repo — push here)
upstream    → https://github.com/TechJam2026/techjam-conversational-search.git
              (fetch-only; never push here)
```

Keep it this way: pull organiser updates with `git fetch upstream` and
merge/cherry-pick deliberately (never `git push upstream`); push team work
only to `origin`.

---

# Stretch Goals / Bonus Backlog

**Not required for a working submission.** Nobody is assigned one of
these by default — they exist for whoever finishes their core deliverables
early and wants to grab something extra. Pick one, post in the group chat
so two people don't build the same thing, do it in its own branch, and PR
it like anything else. None of these should ever delay M0–M6 — if core
work and a stretch goal both need attention, core work wins.

| Idea | What it is | Roughly whose area | Why it's worth doing (if you have time) |
|---|---|---|---|
| **Agent Trace Viewer** | See P5-D6 above — this is the flagship stretch goal, already spec'd | P5, but anyone can build it | Best visible payoff for the demo video/judges relative to effort |
| Reliability harness | A script that deliberately breaks things (no catalog, no LLM key, malformed `user_message`, empty candidate pool) and asserts the Agent always returns a valid contract-conformant response | P5 | Cheap proof of robustness — good Feasibility/Technical Execution talking point |
| CI config | GitHub Actions running `pytest` on every PR | P5 | Catches a broken merge before it reaches `main`; not needed for a small team moving fast, but free credibility |
| Scenario-targeted `next_experiments()` | Make `neeshops/research/optimizer.py::next_experiments()` actually read `scenario_metrics` and target the weakest scenario instead of random sampling | P4 | Turns the research loop from "random search" into something you can honestly call intelligent in the writeup |
| Query rewriting for Browsing | Light rewriting of vague Browsing messages ("something nice for a casual weekend") into a richer retrieval query before hitting BM25/semantic | P2 or P3 | Directly targets Browsing Hit Rate@10, which the weak baseline is worst at |
| Size/style/feature metadata filters | Extend `neeshops/retrieval/filters.py::DEFAULT_FILTERS` beyond budget/category/color/material/brand | P2 | Rounds out constraint coverage without new architecture |
| Latency/cost report per turn | Extend the structured logs to summarize p50/p95 `agent.respond` latency and total token usage across a full evaluator run | P4 or P5 | Feasibility & Practicality judging criterion cares about this explicitly |
| Frontend ↔ live Agent wiring | A tiny local API so `frontend/` can send a real message to a real `NeeShopsAgent` and show a real response, instead of static mock data | P5, only if everything else is done | Nice demo polish; explicitly optional per `docs/neeshops/PROJECT_OVERVIEW.md` — never a required deliverable |
| Team-contributions writeup automation | A script that summarizes `git log --author` per person into the README's contributions section | Anyone | Saves 10 minutes at submission time, zero risk |

If you think of something not on this list, the bar is: **does it improve
a real, measurable thing (Hit Rate@10 / MRR / MTTC / reliability /
judge-visible clarity), and can you build it without touching someone
else's in-progress work?** If yes to both, go for it and post about it.
