# Two-Day Full-Scope Build Plan

This schedule keeps the complete NeeShops scope. It assumes five people can
work in parallel for two long hackathon days, the catalog can be downloaded,
and the team integrates several times instead of waiting until the end.

It is an aggressive plan, not a guarantee. Beginner-friendly means every
block has a visible result and a stop condition; it does not make the amount
of work smaller.

## Before the event clock

Everyone:

```bash
python scripts/download_catalog.py
python scripts/check_readiness.py
pytest -q
```

P5 records:

- Python version;
- current branch and commit;
- readiness output;
- initial full-test result.

P2 starts `python scripts/setup_catalog.py` once so the BM25 index is ready.
P4 preserves the untouched upstream starter in a temporary clean checkout or
separate baseline entry point. The official weak baseline and the current
NeeShops candidate are different systems and must be recorded separately.

## Day 1, block 1 — understand and prove the starting point (hours 0–2)

| Person | Work | Visible result before moving on |
|---|---|---|
| P1 | Read public simulator replies and write route/constraint tests for all four scenarios | New focused tests run; current failures are understood |
| P2 | Build/query the real 50k BM25 index; inspect real catalog field shapes | Three real queries return sensible valid `parent_asin` values |
| P3 | Trace `Candidate -> Recommendation -> starter response`; design LLM response schema | Heuristic ranker tests pass and bounded LLM input/output format is written |
| P4 | Run untouched official weak baseline and current NeeShops initial candidate on the same public set | Two clearly labelled metric files exist locally |
| P5 | Add strict schema/integration tests using non-empty fixture recommendations | Invalid `top_k`, invalid keys, and fallback output are caught by tests |

### Checkpoint A

Meet for 15 minutes. P4 reads the starting metrics aloud. P5 confirms the
official evaluator was not changed. Every person states the one shared
interface they consume and provide.

## Day 1, block 2 — build each full feature path (hours 2–6)

### P1: conversation intelligence

- Extract category, material, color, size, style, brand, budget, feature, and
  use-case values where inferable.
- Recognize evaluator-style “no additional preference” language.
- Test replacement of old values by new values across more than color.
- Test Buying/Browsing routing for all scenario archetypes.
- Make clarification skip answered, previously asked, and no-preference fields.

### P2: full hybrid retrieval

- Keep real-schema weighted BM25 working.
- Implement an in-memory semantic index over catalog text.
- Build/load the index once rather than once per turn.
- Return `Candidate` values through the existing `Retriever` interface.
- Extend filters for size, style, feature, and use case where catalog text
  supports them.
- Add semantic and hybrid tests, including disabled/unavailable behavior.

### P3: full ranking path

- Keep deterministic heuristic ranking as the permanent fallback.
- Implement bounded LLM reranking with structured parsing.
- Read secrets only through settings/environment variables.
- Return token counts to the integration layer.
- Add timeout, malformed-output, missing-key, and disabled-path tests.
- Compare reranked order with retrieval-only order.

### P4: comparable experimentation

- Create the deterministic 160/40 split.
- Record a baseline on the same split used by each experiment.
- Correct accept/reject semantics so ties are not improvements.
- Make `next_experiments()` inspect scenario metrics and form a targeted
  proposal.
- Record configuration, metrics, latency, tokens, dataset, and commit.

### P5: correct orchestration and fallback seams

- Apply current-turn state before current-turn filtering and clarification.
- Build a retrieval query from active state plus the newest message.
- Deduplicate already shown products where appropriate.
- Integrate semantic and LLM availability without breaking deterministic
  behavior.
- Keep internal fields out of the official response.
- Add four-scenario end-to-end fixture tests.

### Checkpoint B

Merge P1 first, then P2, then P3 through P5's integration branch. After each
merge:

```bash
pytest -q
python scripts/run_baseline.py
```

P4 starts a short evaluator run after P2 and again after P3. Do not wait for
every feature before finding integration errors.

## Day 1, block 3 — first complete integration (hours 6–10)

Everyone works from the same integrated commit.

| Person | Integration duty |
|---|---|
| P1 | Inspect failed Boundary/Override sessions and fix state transitions |
| P2 | Inspect missed targets and candidate recall before ranking |
| P3 | Inspect cases where target was retrieved but ranked outside Top 10 |
| P4 | Produce overall and per-scenario comparison with latency/token totals |
| P5 | Fix crashes, contract errors, configuration mismatch, and fallback gaps |

### End-of-Day-1 gate

Do not finish Day 1 without all of the following:

- full tests green on the integrated commit;
- real catalog and evaluator complete without exceptions;
- all four scenario families have an end-to-end test;
- deterministic no-key/no-network path works;
- semantic path has run at least once on the real catalog;
- LLM path has either run against the selected provider or against a faithful
  fake client with parsing/fallback tests;
- metrics saved with their dataset and commit.

## Day 2, block 1 — diagnose and improve (hours 10–14)

P4 gives each owner a failure list, not just an aggregate score:

- P1 gets incorrect questions, state, overrides, and boundary failures.
- P2 gets target-not-in-candidate-pool failures.
- P3 gets target-in-pool-but-poorly-ranked failures.
- P5 gets exceptions, invalid output, high-latency, and fallback failures.

Each owner changes one hypothesis at a time. P4 reruns the same development
split and records the result. Do not accept a configuration because it “looks
better” in one hand-picked conversation.

### Checkpoint C

Select the best integrated configuration using development results. Run the
40-session holdout once. If holdout drops sharply, return to the last stable
configuration and diagnose overfitting.

## Day 2, block 2 — research loop and reliability (hours 14–18)

| Person | Work |
|---|---|
| P1 | Edge wording, repeated questions, remaining-turn behavior |
| P2 | Semantic index load time, memory, retrieval latency, candidate diversity |
| P3 | LLM token/latency bounds, parsing reliability, deterministic fallback quality |
| P4 | Scenario-targeted proposals and readable accepted/rejected experiment log |
| P5 | Missing catalog/key/model simulations, response schema, clean-checkout rehearsal |

At the end of this block, freeze shared interfaces and algorithm structure.
Only evidence-backed parameter changes and reliability fixes should land
after the freeze.

## Day 2, block 3 — demo and submission (hours 18–22)

### P5 builds the Agent Trace Viewer

Use real structured events to show:

- current user message;
- detected route;
- extracted and active constraints;
- clarification decision;
- BM25/semantic candidate counts;
- ranking path and fallback status;
- final recommendations and reasons;
- latency and token usage.

### P4 finalizes evidence

- final development and holdout metrics;
- per-scenario metrics;
- model/provider and version;
- average and high-percentile latency;
- total token usage and estimated cost;
- accepted and rejected experiments.

### Everyone contributes to the writeup

- P1: conversation design and boundary/override behavior;
- P2: retrieval/index design and resource use;
- P3: reranking, personalisation, LLM safety/fallback;
- P4: evaluation method and measured results;
- P5: architecture, integration, limitations, and reproduction.

## Final two-hour checklist

From a clean checkout or a teammate's machine:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/download_catalog.py
python scripts/check_readiness.py
pytest -q
python3 -m evaluator.local_evaluator
```

Then confirm:

- `git status --short` shows no secret or generated artifact;
- evaluator and official labels were not modified;
- response recommendations contain only allowed fields;
- no feature requires an undocumented key or service;
- no-network fallback completes;
- demo uses a real Agent run, not illustrative metrics;
- README contains setup, reproduction, limitations, cost, and contributions;
- final metrics include dataset, config, commit, and date.

## Merge order

Use this order because later modules consume earlier outputs:

```text
P1 state/constraints
  -> P2 retrieval
  -> P3 ranking
  -> P5 integration
  -> P4 measured configuration decisions
  -> P5 final reliability and demo
```

P4 works throughout, but configuration changes are accepted only against an
integrated commit. P5 should merge small complete changes at Checkpoints A,
B, and C, not one giant change at the end.

## Honest risk rule

Full scope in two days is high risk for beginners. If a feature is temporarily
broken during integration, leave its feature flag off while fixing it so the
team can continue testing the other paths. The feature remains in scope and
must still meet its acceptance card before final submission; a feature flag is
a safety mechanism, not a scope cut.
