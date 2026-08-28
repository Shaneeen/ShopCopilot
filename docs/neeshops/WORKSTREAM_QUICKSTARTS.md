# Beginner Workstream Quickstarts

Pick your assigned section. You do not need to understand every module before
starting. Each card states what you own, what you should not touch, the order
to work in, and what evidence proves completion.

For the full responsibilities and merge policy, see `TEAM_WORKSTREAMS.md`.
For shared function signatures, see `INTEGRATION_CONTRACTS.md`.

## P1 — Conversation Intelligence and State

### Your goal

Turn shopper messages into correct, remembered information and useful
questions. You improve all four scenarios before search begins.

### Read these files first

1. `neeshops/conversation/README.md`
2. `neeshops/models/session.py`
3. `neeshops/conversation/constraints.py`
4. `neeshops/conversation/intent.py`
5. `neeshops/conversation/clarification.py`
6. `tests/test_state.py` and `tests/test_intent_override.py`

### Do not edit

`evaluator/`, retrieval implementations, rankers, or `starter/agent.py`.

### Build in this order

1. Add table-driven extraction tests using evaluator-like sentences.
2. Extend extraction one field at a time: category, material, size, style,
   brand, feature, use case, then richer budgets and no-preference wording.
3. Add route tests for Buying, Browsing, Override, and Boundary examples.
4. Add intent-override tests for at least color, material, brand, and budget.
5. Verify clarification never repeats answered, asked, or `NO_PREFERENCE`
   fields.
6. Ask P5 to verify the new state is applied before retrieval on the same
   turn.

### Focused command

```bash
pytest -q tests/test_state.py tests/test_intent_override.py tests/test_agent_smoke.py
```

### Done evidence

- all declared fields have either working extraction or a documented reason
  they require LLM assistance;
- four scenario archetypes are tested;
- old values are replaced, not accumulated;
- boundary replies stop repeat questions;
- module README lists actual coverage.

## P2 — Retrieval and Candidate Generation

### Your goal

Make the hidden target appear in the candidate pool using keyword search,
semantic meaning, and catalog metadata.

### Read these files first

1. `neeshops/retrieval/README.md`
2. `neeshops/retrieval/base.py`
3. `neeshops/retrieval/bm25.py`
4. `neeshops/retrieval/semantic.py`
5. `neeshops/retrieval/candidate_merge.py`
6. `neeshops/retrieval/filters.py`
7. `tests/test_retrieval.py`

### Do not edit

`evaluator/`, conversation logic, rankers, or `starter/agent.py`.

### Build in this order

1. Run `python scripts/setup_catalog.py` and inspect three real searches.
2. Compare BM25 field weights/token handling with the official starter.
3. Choose and document one lightweight local embedding approach.
4. Add only the required dependency and pin a tested compatible version.
5. Build product embeddings once, persist/load the index safely, and search
   with cosine similarity or a lightweight ANN implementation.
6. Return the existing `Candidate` type and keep `is_available()` fail-soft.
7. Test hybrid deduplication, weighting, disabled semantic mode, corrupt or
   missing index, and real-catalog latency.
8. Extend text-backed filters without pretending sparse metadata is complete.

### Focused command

Before creating the new semantic test file:

```bash
pytest -q tests/test_retrieval.py tests/test_agent_smoke.py
```

Create `tests/test_semantic_retrieval.py` as part of this work, then include it
in the focused command.

### Done evidence

- BM25 works on 50,000 products;
- semantic retrieval returns meaningful valid IDs;
- the index is not rebuilt every turn;
- hybrid results are deterministic for a fixed configuration;
- failure falls back to BM25;
- candidate recall and latency are recorded.

## P3 — Ranking, Query Intelligence, and Personalisation

### Your goal

Move a retrieved target as high as possible while preserving a reliable
deterministic path when an LLM is unavailable.

### Read these files first

1. `neeshops/ranking/README.md`
2. `neeshops/ranking/base.py`
3. `neeshops/ranking/heuristic.py`
4. `neeshops/ranking/llm_reranker.py`
5. `neeshops/personalization/profile.py`
6. `tests/test_ranking.py`

### Shared seam

You own the ranker, but P5 owns `neeshops/agent.py`. Agree on availability,
token-usage, and fallback behavior before both people edit that seam.

### Build in this order

1. Add an identity/pass-through comparison so heuristic ranking has a measured
   MRR delta.
2. Define a small structured LLM output containing known candidate IDs only.
3. Limit the number and text length of candidates sent to the model.
4. Add the selected provider SDK and document its environment variables.
5. Implement timeout, parsing, unknown-ID rejection, duplicate removal, and
   token accounting.
6. Return unranked candidates through `HeuristicRanker` after any failure.
7. Test that explicit user constraints remain stronger than profile tags.
8. Give P4 model name, latency, token totals, and estimated cost.

Create `tests/test_llm_reranker.py` for enabled, disabled, malformed-output,
timeout, and fallback behavior.

### Focused command

```bash
pytest -q tests/test_ranking.py tests/test_agent_smoke.py
```

### Done evidence

- deterministic ranker always works;
- LLM path works when enabled;
- missing key, timeout, malformed JSON, duplicate IDs, and unknown IDs all
  fall back safely;
- token use is returned through the official `usage` field;
- MRR comparison and cost are recorded.

## P4 — Research, Evaluation, and Experimentation

### Your goal

Make every performance claim reproducible. You decide whether configuration
changes are improvements using comparable data, not intuition.

### Read these files first

1. `docs/competition_specification.md`
2. `evaluator/local_evaluator.py` — read only
3. `neeshops/research/README.md`
4. `scripts/evaluate.py`
5. `scripts/run_experiment.py`
6. `tests/test_research.py`

### Never edit

`evaluator/` or public labels. Do not edit another owner's algorithm just
because one experiment underperformed.

### Build in this order

1. Reproduce the official weak starter in a separate clean baseline path.
2. Run the current NeeShops candidate separately; do not call it the official
   baseline.
3. Generate the deterministic 160/40 split.
4. Record a baseline on the exact same dataset used by candidate experiments.
5. Add dataset path/hash, commit, strategy, latency, tokens, and scenario
   metrics to each experiment record.
6. Reject ties and require an explicit minimum improvement.
7. Make `next_experiments()` target the weakest scenario with a written
   hypothesis.
8. Run holdout only at checkpoints and record the generalisation gap.

### Focused command

```bash
pytest -q tests/test_research.py tests/test_evaluator.py
```

### Done evidence

- official and NeeShops starting scores are clearly separated;
- baseline and candidate always use the same dataset;
- at least one targeted experiment is accepted or rejected with evidence;
- experiment log includes scenarios, latency, tokens, config, commit, and
  dataset;
- holdout result is recorded without repeatedly tuning on it.

## P5 — Integration, Reliability, and Delivery

### Your goal

Make every workstream operate together through the exact official interface,
then make the behavior understandable in the demo.

### Read these files first

1. `docs/agent_api_contract.json`
2. `docs/neeshops/INTEGRATION_CONTRACTS.md`
3. `starter/agent.py`
4. `neeshops/agent.py`
5. `tests/test_agent_contract.py`
6. `tests/test_agent_smoke.py`

### Do not do

Do not copy P1–P4 algorithms into `neeshops/agent.py`. Orchestration should
call their modules. Never add internal fields to the official response.

### Build in this order

1. Add strict response-schema tests with non-empty recommendations and
   `top_k=10`.
2. Correct the turn sequence so extracted constraints update state before
   current-turn retrieval, filtering, and clarification.
3. Build queries from active constraints/history plus the newest message.
4. Agree with P3 on a ranker result/token-usage seam and safe fallback.
5. Add end-to-end tests for Buying, Browsing, Override, and Boundary.
6. Test missing catalog, missing model/key, retrieval failure, reranker
   failure, empty query, and malformed user input.
7. Capture real structured events and render the Agent Trace Viewer.
8. Rehearse setup and evaluation from a clean checkout.

### Focused command

```bash
pytest -q tests/test_agent_contract.py tests/test_agent_smoke.py tests/test_evaluator.py
```

### Done evidence

- official schema validated with non-empty output;
- all four scenarios pass end to end;
- optional failures return valid deterministic output;
- full evaluator finishes and metrics are archived;
- clean-checkout instructions work;
- real Agent trace, final limitations, and team contributions are documented.

## Shared review checklist

Before asking for a merge, paste this into the pull request:

```text
[ ] I changed only my owned files, or named the shared files explicitly.
[ ] I added/updated a test for the behavior.
[ ] Focused tests pass.
[ ] Full pytest -q passes.
[ ] I did not edit evaluator/ or public labels.
[ ] I did not commit a key, catalog, index, result artifact, or .env.
[ ] I updated the module README if behavior changed.
[ ] I told consumers if an interface changed.
[ ] I included the command and output that prove the acceptance check.
```
