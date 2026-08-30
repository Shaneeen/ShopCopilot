# Person 3B — Personalisation & Evaluation

Other half of the original **Person 3** workstream. See
[README.md](./README.md) for how this relates to 3A, and
[HOW_A_AND_B_WORK_TOGETHER.md](./HOW_A_AND_B_WORK_TOGETHER.md) for
concurrency rules.

## Owned folders

`neeshops/personalization/`.

## Allowed/shared interfaces

Provides: `personalization_boost` (see
`docs/neeshops/INTEGRATION_CONTRACTS.md` → "Profile ↔ Ranking"). Consumes:
`ConversationState.user_profile`, and `Ranker` output from 3A (read-only,
for the P3-D5 comparison experiment).

## Files to avoid modifying

`neeshops/retrieval/`, `neeshops/conversation/`, `neeshops/ranking/` (3A's
folder), `starter/agent.py`, `evaluator/`.

## Responsibilities

- Soft user-profile signals via `personalization_boost()`.
- Query rewriting where appropriate (if not already covered upstream).
- P3-D5: comparing ranking-strategy output against retrieval-only output
  and reporting the MRR delta — this reads 3A's ranker output but does not
  modify `neeshops/ranking/`.

## Deliverables

- **P3-D2** — Personalisation converts the official aggregate profile into
  **soft** ranking features; explicit constraints take priority.
  *Acceptance*: `personalization_boost()` + `ranking.personalization_weight`
  (default 0.15) — **already done**; verified by
  `tests/test_ranking.py::test_personalization_never_overrides_explicit_low_retrieval_score`.
- **P3-D5** — Compare ranking strategy against retrieval-only output.
  *Acceptance*: a script or experiment (coordinate with P4) that runs the
  evaluator with `HeuristicRanker` vs. an identity ranker (pass-through
  retrieval order) and reports the MRR delta — **done**, see
  `scripts/evaluate_ranking_ab.py` and the results under
  `evaluation/results/`.

## Success metrics

MRR delta (ranked vs. retrieval-only), reported as an actual measured
number, never estimated.

## Merge checklist

- [ ] `pytest tests/test_ranking.py tests/test_agent_smoke.py` passes
- [ ] No numeric confidence fabricated in `reason` strings
- [ ] P3-D5 comparison script runs against the current `HeuristicRanker`
      output (re-run after 3A merges `LLMReranker` changes, since the
      comparison baseline may shift)

## Definition of Done

`neeshops/personalization/README.md` updated, P3-D5 comparison
script/experiment lands with a reported MRR delta.

## First action

Coordinate with P4 on the evaluator harness, then draft the
retrieval-only "identity ranker" used as the P3-D5 baseline.

## Shared file: `neeshops/agent.py`

3B may touch this file to wire `personalization_boost` output into the
pipeline. 3A owns the ranker-selection logic in the same file — see
[HOW_A_AND_B_WORK_TOGETHER.md](./HOW_A_AND_B_WORK_TOGETHER.md) for how to
avoid collisions.

---

## Technical guide

### How personalisation works

Personalisation is applied per candidate row via
`neeshops.personalization.profile.personalization_boost()`:

```python
def personalization_boost(product_row: dict[str, Any], profile: UserProfile) -> float:
    # Matches tags in user_profile against product_row categories or details
    # Returns a float boost in [0.0, 1.0]
```

The boost is scaled by `ranking.personalization_weight` (default `0.15`,
configured in [`neeshops/config/default_strategy.json`](../../neeshops/config/default_strategy.json))
and added to the candidate's score inside `HeuristicRanker`.

### How to run evaluation

Local baseline check:

```bash
python scripts/run_baseline.py
```

Sweep personalization weights:

```bash
python scripts/evaluate_personalization_weights.py
```

Ranked vs. identity (retrieval-only) A/B comparison for P3-D5:

```bash
python scripts/evaluate_ranking_ab.py
```

Check results and MRR deltas in the console output, and in
`evaluation/results/personalization_weight_sweep.md` /
`evaluation/results/personalization_case_analysis.md`; record accepted
configurations in `docs/neeshops/EXPERIMENTS.md`.

### Key files

- Personalisation logic: [`neeshops/personalization/profile.py`](../../neeshops/personalization/profile.py)
- Tuning config: `ranking.personalization_weight` in [`neeshops/config/default_strategy.json`](../../neeshops/config/default_strategy.json)
- Personalisation unit tests: [`tests/test_ranking.py`](../../tests/test_ranking.py) (constraint-override behavior) and [`tests/personalization/`](../../tests/personalization/)
- Evaluation entrypoints: [`scripts/evaluate.py`](../../scripts/evaluate.py), [`scripts/evaluate_ranking_ab.py`](../../scripts/evaluate_ranking_ab.py), [`scripts/evaluate_personalization_weights.py`](../../scripts/evaluate_personalization_weights.py)
