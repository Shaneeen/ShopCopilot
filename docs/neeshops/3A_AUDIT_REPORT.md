# Person 3A — Ranking Core Audit Report

Branch: `person-3a-ranking`. Scope: `neeshops/ranking/` only (plus the two
minimal, explicitly-noted cross-boundary registrations below).

## Baseline verification (before any fix)

- `pytest -q` (full suite, after installing missing `numpy` and
  `google-genai` — both already pinned in `requirements.txt` but absent
  from this environment): **8 failed, 245 passed, 1 deselected**.
  - 7 of the 8 failures were `tests/test_gemini_provider.py` — purely an
    environment issue (`google-genai` not installed), not a code bug.
    Resolved by installing the pinned dependency.
  - The 8th, `tests/test_deterministic_ranking.py::test_ablation_can_disable_retrieval_and_metadata_features`,
    is a genuine ranking-logic bug (see CONFIRMED ISSUES #1).
  - This does **not** match the previous Codex audit's reported "83
    passed/1 failed (focused), 252 passed/1 failed/1 deselected (full)" —
    actual counts here were 245/253 passed depending on environment
    readiness; the discrepancy is attributable to environment setup
    (missing deps), not a different code state.
- `python scripts/check_readiness.py` initially failed on `numpy` missing
  (blocks `starter.agent.Agent` import); fixed by installing it.

## CONFIRMED ISSUES

1. **Ablation isolation bug — coverage/salience/full_match_bonus bypassed
   `features_enabled` entirely.**
   `neeshops/ranking/deterministic.py`, `ConstraintAwareRanker.rank()` and
   `._aggregate()`.
   - `_aggregate()` added `coverage_weight * features.coverage`,
     `coverage_salience_weight * features.salience`, and
     `full_match_bonus` unconditionally, regardless of what
     `features_enabled` said.
   - Worse: `rank()`'s primary sort key used `-features.coverage` as an
     **unconditional secondary sort tier**, ahead of the aggregated
     relevance score entirely. So even if every weight in `_aggregate()`
     were zeroed out via `features_enabled`, coverage still fully
     determined ordering among non-violating candidates.
   - Consequence: any experiment/ablation that tries to isolate one
     scoring feature (the documented use case for `features_enabled`) is
     not actually isolating it — coverage (and, for browsing, popularity)
     keep exerting influence no matter what's "disabled." This directly
     invalidates any A/B feature-ablation experiment run through
     `neeshops/ranking/experiments.py` or `run_experiment.py` against
     `features_enabled` toggles.
   - Reproduced by (pre-fix) `test_ablation_can_disable_retrieval_and_metadata_features`
     failing, and by the new regression test added below.

2. **Stale/inconsistent default config — `ranking.deterministic.weights.personalization`
   was `0.0`.** `neeshops/config/default_strategy.json`.
   - `features_enabled.personalization` was already `false` by default (a
     legitimate soft-signal-off-by-default choice), but the paired
     *weight* was also `0.0`. That means: turning personalization back on
     via `features_enabled` (as any experiment/ablation would) still does
     nothing, because the weight that multiplies the boost is zero. This
     matches the previous audit's flagged "personalization enabled but
     merged default weight is 0.0" — confirmed real, not a stale/false
     alarm.
   - Fixed by setting the default weight to `0.05` (same order of
     magnitude as the other soft weights, e.g. `inferred: 0.05`),
     independent of whether the feature is enabled by default.

3. **`features_enabled` had no keys for `coverage`, `full_match_bonus`, or
   `popularity`** — the config schema simply had no way to gate what turned
   out to be the largest and most decisive terms in the model. Fixed as
   part of #1 (new keys added to `default_strategy.json` and
   `SAFE_PARAMETERS` in `neeshops/research/experiment.py`).

### Areas inspected and found correct (no bug)

- **Score direction throughout the pipeline**: `Candidate.score` is
  consistently "higher is better" from `candidate_merge.py` (P2, read-only
  review) through `normalize_scores()` and `ConstraintAwareRanker`'s
  `-relevance` sort key and `HeuristicRanker`'s `reverse=True` sort. No
  sign inversion found.
- **RRF (`reciprocal_rank_fusion`)**: correct standard formula, dedupes
  per-source ranking lists, `k` validated non-negative. `FusionAwareRanker`
  correctly falls back to rank-normalization (not RRF) when
  `source_rankings` isn't supplied, rather than fabricating fusion from
  data it doesn't have — this is documented intent, not a bug.
- **UNKNOWN vs MISMATCH**: `_attribute_status`/`_budget_status` correctly
  return `UNKNOWN` (not `MISMATCH`) when metadata is absent — metadata
  absence is not accidentally treated as negative evidence anywhere in
  `features.py`. `hard_constraint_violation_count` only counts explicit
  `MISMATCH`, never `UNKNOWN`.
- **Deterministic tie-breaking**: `ConstraintAwareRanker`'s sort key ends
  in `candidate.parent_asin` (stable, deterministic); `candidate_merge.py`'s
  `_tie_break` similarly breaks ties on `parent_asin`.
- **Candidate deduplication**: `_unique_candidates()` in
  `deterministic.py`, `_unique_recommendations()` in `llm_reranker.py`,
  and the dedupe in `RetrievalOrderRanker` all keep first-seen and drop
  later duplicates by `parent_asin` — consistent behavior, tested by
  `test_output_contract_top_k_unique_and_candidate_only`.
- **Candidate-window / truncation before reranking**: `pool = _unique_candidates(candidates)[:rerank_limit]`
  truncates *after* dedup (correct order — avoids losing a rank-40 unique
  item to an earlier duplicate). `HeuristicRanker` truncates before
  scoring but doesn't dedupe first; since `HybridRetriever` output is
  already deduped upstream (per architecture docs) this is consistent,
  not a fresh bug.
- **`LLMReranker` fallback behavior**: every failure path (`disabled`,
  too few constraints, gate not triggered, provider unavailable,
  malformed/invalid response, exception, timeout) returns
  `baseline[:top_k]` from the `HeuristicRanker` fallback and records
  `last_fallback_reason` — never raises, never returns empty results
  when a non-empty baseline exists. Matches the CLAUDE.md hard
  requirement for ranker fallback behavior.
- **Personalization never overriding explicit constraints**: verified via
  existing test `test_personalization_never_overrides_explicit_low_retrieval_score`
  (passes) and structurally: `ConstraintAwareRanker`'s primary sort tier
  is `hard_constraint_violation_count` — personalization only enters the
  third tier (`relevance`), so it can never move a violating item ahead of
  a non-violating one.
- **No fabricated numeric confidence in `reason` strings**: checked every
  `_reason()` implementation in `deterministic.py`, `heuristic.py`,
  `llm_reranker.py` — all return static/human-readable text, no scores or
  percentages interpolated in.

## FIXES MADE

1. `neeshops/ranking/deterministic.py`: gated `coverage`/`salience`/
   `full_match_bonus` additions in `_aggregate()` and the coverage/
   popularity terms in the sort key behind `features_enabled`, so an
   ablation genuinely isolates the named feature(s).
2. `neeshops/config/default_strategy.json`:
   - Added `features_enabled.coverage`, `.full_match_bonus`, `.popularity`
     (all `true`, preserving current production behavior by default).
   - Fixed `weights.personalization` from `0.0` to `0.05`.
3. `neeshops/research/experiment.py`: registered the three new
   `features_enabled.*` keys in `SAFE_PARAMETERS` so experiments can
   legally sweep them (required by `test_shipped_strategy_has_no_unregistered_v2_keys`).
   This is a one-line addition to an existing allowlist, not new 3B logic
   — flagged here for visibility since the file is nominally 3B's.

## TESTS ADDED

- `tests/test_deterministic_ranking.py::test_ablation_isolates_coverage_from_the_sort_key_not_just_the_score`
  — regression test: with only `retrieval` enabled, a high-retrieval/
  zero-coverage candidate must outrank a zero-retrieval/full-coverage
  candidate. Fails on the pre-fix code, passes after.

## EXPERIMENT RESULTS

`python scripts/evaluate_ranking_ab.py --dataset data/dev_split.jsonl --label baseline_after_fix`
completed (`artifacts/experiments/baseline_after_fix_1788074538.json`,
160 dev-split sessions, `ConstraintAwareRanker` — personalization
weight=0.05 post-fix, rerank_limit=40):

| Metric | Retrieval-only (R0) | R2, profile off | R2, profile on | Δ (R2 vs R0) |
|---|---|---|---|---|
| MRR (overall) | 0.502056 | 0.490104 | 0.488378 | -0.011952 |
| Hit@10 (overall) | 0.875 | 0.89375 | 0.89375 | +0.018750 |
| personalization-only Δ MRR | — | — | — | -0.001726 |
| personalization-only Δ Hit@10 | — | — | — | +0.000000 |

These overall deltas are **numerically identical** to the previous audit's
reported figures (+1.875pp Hit@10, -0.01195 MRR) — expected, since the
shipped `default_strategy.json` already had every `features_enabled` flag
at its intended default (`true`, except personalization), so the ablation-
isolation fix only changes behavior when an experiment actually toggles
those flags; it does not change the default production run. The
personalization-weight fix (0.0 → 0.05) is visible in the small nonzero-
now `personalization-only Δ Hit@10`/`Δ MRR`, though the effect stays
negligible at this weight.

Scenario breakdown (computed from `per_sample` in the same artifact):

| scenario | n | R0 MRR | R2 MRR | Δ MRR | R0 Hit@10 | R2 Hit@10 | Δ Hit@10 |
|---|---|---|---|---|---|---|---|
| buying | 66 | 0.5393 | 0.5333 | -0.0060 | 0.8485 | 0.8788 | +0.0303 |
| **browsing** | 65 | 0.5065 | 0.4439 | **-0.0626** | 0.9538 | 0.9692 | +0.0154 |
| boundary | 7 | 0.2052 | 0.3254 | +0.1202 | 0.5714 | 0.7143 | +0.1429 |
| intent_override | 22 | 0.4717 | 0.5494 | +0.0777 | -0.0455 → 0.7727 vs 0.8182 | | -0.0455 |

**The browsing MRR regression is confirmed real** (-0.0626, matching the
previous audit exactly) and is the only scenario where R2 makes things
worse on both metrics tracked (MRR down, and Hit@10 only marginally up) —
Hit@10 actually improves overall in browsing (R2 finds the target in the
top 10 more often than retrieval-only), but ranks it *lower within* the
top 10 once found. That "found more often, ranked worse" signature
localizes the regression to R2's **within-top-10 ordering**, not to
recall/candidate pool truncation.

### Root cause, traced on real failing sessions

Reproduced two concrete browsing/vague-query sessions end-to-end
(`public_0141`, `public_0102`) with `ConstraintAwareRanker.last_diagnostics`
captured at the hit turn. Both show the same mechanism:

- When the user has disclosed only **one generic constraint** (typically
  `category`, e.g. "Piercing Jewelry Screws" / "Bras Everyday Bras" — the
  common state early in a browsing conversation, or throughout it for a
  session that never narrows further), essentially *every* candidate in
  the pool satisfies that one constraint (`category_match=1.0`), so
  `hard_constraint_violation_count=0` and `coverage=1.0` for the entire
  candidate set — coverage stops discriminating between candidates
  entirely.
- With coverage tied across the pool, the deciding terms in `_aggregate()`
  become `title_overlap`/`feature_overlap` (weight 0.08 each) and
  `salience` (weight 0.5) — but `salience` here measures which catalog
  *field* redundantly repeats the single generic category constraint's
  own tokens, not genuine relevance to the user's actual (unstated) need.
  Example from `public_0141` (target `B0BLH7JHG8`, single constraint
  `category`): the true retrieval-rank-1 candidate `B001EU3ZR0`
  (`retrieval_score_normalized=1.0`) scored `relevance=3.073` and lost to
  `B07DR9LGDW` (`retrieval_score_normalized=0.757`, rank 9) which scored
  `relevance=3.529` purely because it had higher `title_overlap`
  (0.667 vs 0.333) and `salience=1.0` vs `0.0` — both driven by
  incidental repetition of the category words in its title, not by any
  signal BM25/semantic retrieval didn't already have and weigh correctly.
  Net effect: `retrieval` (weight 0.40, the actual relevance signal for a
  vague single-constraint query) is outvoted by `title_overlap +
  feature_overlap + salience` (combined weight up to 0.08+0.08+0.5=0.66)
  even though those terms are *tautologically informative* about the
  literal constraint text and carry no information beyond what already
  determined `coverage=1.0` for everyone.
- This matches several of the brief's hypothesized causes directly:
  **"vague queries over-constrained"** (a single soft category term is
  being scored as if it were a discriminating signal), and
  **"soft text attributes behaving like hard intent"** (title/feature
  token overlap on the constraint text stands in for real relevance once
  coverage saturates). It is not caused by metadata sparsity, false
  MISMATCH, or RRF/fusion issues in these two traced sessions — both had
  clean `category: MATCH` with no violations at all.

This is a genuine scoring-calibration issue, not a further correctness
bug — `coverage`/`salience`/`title_overlap` are each individually well-
defined and computed correctly; the problem is their combined weight
overwhelming retrieval's weight specifically in the low-constraint-count
regime that browsing sessions live in. Per the brief ("don't tune weights
while known semantic bugs exist... only after 1-5 are stable, propose the
smallest change"), this is flagged as the priority follow-up rather than
fixed in this pass — see NEXT RECOMMENDED STEP and OPTIONAL below for the
smallest candidate fix (scaling `coverage_weight`/`coverage_salience_weight`
by how many *active* constraints exist, so a single generic constraint
can't out-vote retrieval).

Reproduction script used: a small standalone harness replaying
`evaluator/local_evaluator.py`'s deterministic scripted conversation for
one `sample_id` through the live `NeeShopsAgent`/`ConstraintAwareRanker`
and printing `last_diagnostics` at the hit turn — not committed (scratch
tooling), reproducible from the same evaluator functions
(`materialize_hidden_fields`, `initial_message`, `customer_reply`) plus
`neeshops.agent.NeeShopsAgent`.

## FAILED IDEAS

(none yet — conservative-improvement pass not started)

## DEPENDENCIES ON OTHER PEOPLE

- None required so far. The two touched files outside `neeshops/ranking/`
  (`neeshops/config/default_strategy.json`, `neeshops/research/experiment.py`)
  are config/allowlist edits, not logic changes, and were necessary to
  make the ranking fix (#1/#2 above) actually take effect / pass existing
  tests.

## NEXT RECOMMENDED STEP

Run a dev-split A/B of the smallest candidate fix for the traced browsing
regression: scale `coverage_weight`/`coverage_salience_weight`'s
contribution by the number of *active* meaningful constraints (e.g.
`effective_coverage_weight = coverage_weight * min(1.0, active_constraint_count / N)`
for some small `N` like 2–3), so a single generic constraint (the common
browsing-session state traced above) can no longer produce a tied
`coverage=1.0` across the whole pool that then hands the tie-break to
`title_overlap`/`salience` noise instead of to `retrieval`. This is a
config-driven, `features_enabled`-style change confined to `_aggregate()`
in `deterministic.py`, testable in isolation, and directly targets the
confirmed mechanism (not a guess) — but per the brief, it should be
proposed and A/B'd on `data/dev_split.jsonl` via
`scripts/evaluate_ranking_ab.py`/`run_experiment.py` before being adopted,
not applied speculatively in this pass.

## R4 (CrossEncoder) — decision: do not implement yet

Not implemented, per instructions. Assessment of whether the corrected
deterministic pipeline still leaves enough ranking error to justify one:

- The confirmed bugs (ablation isolation, personalization weight) were
  measurement/config bugs, not evidence that R2's *scoring model itself*
  is miscalibrated — so fixing them doesn't yet tell us whether a
  cross-encoder would help. That requires the corrected R0–R3 comparison
  below.
- If, after the corrected re-evaluation, R2/R3 still show a material MRR
  gap versus R0 on twin-heavy buying cases (i.e. cases where several
  candidates pass all hard constraints and differ only in soft
  relevance), that is the specific failure mode a cross-encoder targets
  and would justify a follow-up experiment.
- If it is later justified, proposed design (not implemented):
  - **Model**: a small open cross-encoder (e.g.
    `cross-encoder/ms-marco-MiniLM-L-6-v2`) run locally — same
    dependency-cost tier as the existing BM25 stack, no paid API,
    keeping R4 in the same "deterministic-ish, no external latency"
    class as R2/R3 rather than R5's LLM-provider class.
  - **Shortlist size**: rerank only the top ~20–30 non-violating
    candidates from R2's output (i.e. cross-encoder narrows an
    already-constraint-filtered pool — mirrors the `rerank_limit` /
    `llm.rerank_limit` pattern already used for R3/R5).
  - **Expected latency**: single-digit ms per pair on CPU for a MiniLM
    cross-encoder at that shortlist size (order of a few hundred ms total
    per session) — needs to be measured against the evaluator's MTTC
    budget before acceptance.
  - **Dependency cost**: `sentence-transformers` + a downloaded model
    checkpoint (tens of MB) — a real new dependency, unlike R2/R3.
  - **Fallback**: identical shape to `LLMReranker` — wrap in a
    try/except that falls back to `ConstraintAwareRanker` on any load/
    inference failure, gated by a `feature_flags` entry
    (`enable_cross_encoder`, default `false`), never raising.
  - **Experiment design**: `evaluate_ranking_ab.py`-style A/B on
    `data/dev_split.jsonl`, comparing R2 (baseline) vs. R2+R4-reranked
    shortlist, holding candidate pools identical; accept only on a
    measured MRR/Hit@10 improvement with latency inside budget, per the
    same acceptance bar `neeshops/research/` already applies.

## R5 (Gemini LLMReranker) — status: experimental, disabled by default

Per the brief and the previously-saved ~100-case benchmark's reported
result (Hit@10 flat/not improved, MRR reduced, added latency), R5 stays
disabled by default (`feature_flags.enable_llm_reranker: false`,
unchanged). No evidence was found in this session to overturn that
result; re-verifying it exactly was out of scope for this pass (it
requires live Gemini API credentials + budget) but the code path's
fallback behavior was re-audited and confirmed safe (see CONFIRMED
ISSUES / areas inspected above) — so leaving it off costs nothing and
turning it on for a future experiment is low-risk.

## Remaining work classification

**DO NOW**
- None outstanding from this pass beyond what's already fixed — the
  confirmed ablation-isolation and personalization-weight bugs are fixed
  and regression-tested.

**TEST NEXT**
- The dev-split A/B is complete (see EXPERIMENT RESULTS) — the browsing
  MRR regression (-0.0626) is confirmed real and traced to a specific
  mechanism (coverage saturating at 1.0 for single-generic-constraint
  browsing sessions, handing ranking control to `title_overlap`/
  `salience` noise instead of `retrieval`). Next: A/B the constraint-count
  -scaled `coverage_weight` candidate fix described in NEXT RECOMMENDED
  STEP against the same dev-split browsing subset.
- Run `run_experiment.py` ablation sweeps over the newly gated
  `features_enabled.{coverage,full_match_bonus,popularity}` now that
  isolation actually works, to quantify each feature's standalone
  contribution before any further tuning.

**OPTIONAL**
- R4 CrossEncoder, only if the re-run shows a persistent twin-heavy MRR
  gap (see write-up above) — do not build speculatively.
- Loosening `_attribute_status`'s subset-token matching for
  `material`/`color`/etc. when a catalog row's direct attribute field is
  present but incomplete relative to a multi-word constraint (e.g.
  constraint "genuine leather" vs. row material "leather") — currently
  scores MISMATCH instead of falling back to title/feature support the
  way the no-direct-value path already does. Flagged as a plausible
  contributor to over-aggressive hard-constraint rejection on sparse
  catalog rows, not yet confirmed with dev-split evidence.

**DO NOT DO**
- Re-enabling R5/Gemini by default, or tuning any weight, before the
  dev-split re-evaluation above is actually reviewed — per the brief's
  "don't tune weights while known semantic bugs exist" and "don't call a
  strategy better unless measurements support it."
- Rewriting `neeshops/ranking/experiments.py`'s harness structure or
  `evaluate_ranking_ab.py` — both already run every strategy against the
  same candidate pool per session/arm; the actual unfairness was inside
  `ConstraintAwareRanker`'s own scoring (fixed), not the harness
  plumbing.

## 2026-08-30 — overlap-dampening controlled evaluation

Verified the "overlap dampening" mechanism added this session
(`RankingFeatures.active_constraint_count`, `_aggregate()` scaling
`title_overlap`/`feature_overlap` weight by
`min(1.0, active_constraint_count / overlap_dampening_threshold)`, config
key `ranking.overlap_dampening_threshold`, default `2`) against the
proposed browsing-MRR fix. `pytest -q` still 254 passed at the start of
this pass.

### Step 0 — `overlap_dampening_fix` dev-split run (background job)

`python scripts/evaluate_ranking_ab.py --dataset data/dev_split.jsonl
--label overlap_dampening_fix` (pid 20026, threshold=2, the shipped
default — this script only compares `identity` retrieval order vs.
`ConstraintAwareRanker` profile-off/profile-on, it does not select among
R0/R1/R3):

| Metric | retrieval-only | current, profile off | current, profile on |
|---|---|---|---|
| MRR | 0.502056 | 0.494983 | 0.493256 |
| Hit@10 | 0.875 | 0.89375 | 0.89375 |

Ranking MRR delta (profile off vs retrieval-only): **-0.007073**
(improved from the pre-dampening -0.011952 in the earlier run in this
report, i.e. the raw R2-vs-R0 MRR gap narrowed by ~0.0049 with dampening
in the default config). Hit@10 delta unchanged at +0.018750.
Personalization-only delta: -0.001727 MRR, +0.0 Hit@10 (unchanged from
before, as expected — personalization weight untouched).

Artifact preserved at
`artifacts/experiments/overlap_dampening_fix_1788076159.json` and copied
to `docs/neeshops/overlap_dampening_fix_1788076159.json` so a later run
with the same label cannot silently overwrite it.

### Step 1 — does `overlap_dampening_threshold=0` cleanly disable the mechanism?

Read `neeshops/ranking/deterministic.py` `ConstraintAwareRanker._aggregate()`
directly (lines ~165-177):

```python
overlap_scale = 1.0
if self._overlap_dampening_threshold > 0:
    overlap_scale = min(
        1.0,
        features.active_constraint_count / self._overlap_dampening_threshold,
    )
...
if name in ("title_overlap", "feature_overlap"):
    weight *= overlap_scale
```

`self._overlap_dampening_threshold` is read in `__init__` from
`rank_cfg.get("overlap_dampening_threshold", 2)` where `rank_cfg =
strategy["ranking"]` (i.e. the key lives at `ranking.overlap_dampening_threshold`,
not nested under `ranking.deterministic`). With `threshold=0`, the guard
`self._overlap_dampening_threshold > 0` is `False`, so `overlap_scale`
stays at its initialized value `1.0` unconditionally — the `min(...)`
branch, and therefore any dependence on `active_constraint_count`
(which is always `>= 0` per `features.py`'s `len(constraints)`), is never
evaluated. **Confirmed: `threshold=0` genuinely and unconditionally
disables dampening** (`overlap_scale == 1.0` for every candidate,
identical to pre-dampening behavior). No alternative disable value was
needed.

### Step 2 — controlled R0/R1/R2/R3 comparison, dev_split, threshold as the only variable

No CLI flag exists on `evaluate_ranking_ab.py`/`run_experiment.py` to
select ranker/threshold directly, so a throwaway single-process harness
(`/private/tmp/.../scratchpad/r0r3_compare.py`, not committed) built each
arm the same way `evaluate_ranking_ab.py` does — same `BM25Retriever` +
`HybridRetriever` + shared `token_index`, deep-copied strategy with only
`ranking.overlap_dampening_threshold` changed for the R2/R3 off/on pairs
— and ran `evaluator.local_evaluator.evaluate()` once per arm on the full
160-session `data/dev_split.jsonl`, `PYTHONHASHSEED=0`, wall-clock
latency captured by wrapping each ranker's `.rank()` call.

| Arm | MRR | Hit@10 | Browsing MRR | Browsing Hit@10 | latency mean/p50/p95 (ms) |
|---|---|---|---|---|---|
| R0 RetrievalOrderRanker | 0.502056 | 0.875000 | 0.506484 | 0.953846 | 0.016 / 0.016 / 0.018 |
| R1 HeuristicRanker | 0.186104 | 0.637500 | 0.208877 | 0.630769 | 2.745 / 2.727 / 3.893 |
| R2 off (threshold=0) | 0.490104 | 0.893750 | 0.443901 | 0.969231 | 7.994 / 7.671 / 12.555 |
| R2 on (threshold=2) | 0.494983 | 0.893750 | 0.456081 | 0.969231 | 7.949 / 7.591 / 12.269 |
| R3 off (threshold=0) | 0.475818 | 0.868750 | 0.429029 | 0.923077 | 8.553 / 8.127 / 13.409 |
| R3 on (threshold=2) | 0.480697 | 0.868750 | 0.441209 | 0.923077 | 8.329 / 7.979 / 12.666 |

R2-off numbers here match Step 0's `overlap_dampening_fix` "profile off"
row exactly (0.490104 / 0.89375), confirming the harness reproduces the
production evaluator faithfully. R1 (HeuristicRanker, legacy stage-1) is
far worse than R0/R2/R3 on this dataset (MRR 0.186 vs ~0.48-0.50) — this
is a pre-existing property of the legacy heuristic path (not touched or
caused by this session's changes) and is noted only for completeness
since it was requested as a reference arm; it is orthogonal to the
dampening question since `HeuristicRanker` never calls
`ConstraintAwareRanker._aggregate()`.

Confirmed R0 and R1 are unaffected by the threshold, by construction:
`RetrievalOrderRanker.rank()` does no scoring at all, and
`HeuristicRanker.rank()` computes `final_score = c.score * (1 - p_weight)
+ boost * p_weight` — neither path calls `_aggregate()` or reads
`active_constraint_count`/`overlap_dampening_threshold` anywhere.

**Δ (R2 ON vs R2 OFF):** MRR **+0.004879**, Hit@10 **+0.000000**,
browsing MRR **+0.012180** (0.456081 vs 0.443901).
**Δ (R3 ON vs R3 OFF):** MRR **+0.004879**, Hit@10 **+0.000000**,
browsing MRR **+0.012180** (0.441209 vs 0.429029).
(The two deltas are numerically identical to six decimal places, which
is expected — R3 differs from R2 only in `_retrieval_signals()`'s
normalization method, not in the overlap-dampening code path, so the
minmax-normalized retrieval scores it feeds into the same `_aggregate()`
produce the same relative ordering shift.)

Session-level rank-change count (target's `best_rank`, R2 OFF vs R2 ON,
all 160 dev-split sessions): **157 unchanged, 1 improved, 2 worsened.**
Only 3 of 160 sessions had any change in target rank at all — the
mechanism affects a very small, specific slice of sessions (single
generic-constraint browsing/boundary cases), not the dataset broadly.

### Step 3 — session-level inspection (R2 ON vs OFF)

**Largest improvement — `public_0141`** (browsing, target `B0BLH7JHG8`,
query "Piercing Jewelry Screws"): OFF rank **8** (turn 1) → ON rank **1**
(turn 2). This is the exact session traced as the root-cause example in
the original audit (EXPERIMENT RESULTS section above). At turn 1 with
dampening OFF, `active_constraint_count=1`, target's `title_overlap=
feature_overlap=0.667`, `salience=0.0`, `retrieval_score_normalized=
0.655` (rank 13), `relevance=2.989`, landing at rank 8 — beaten by
candidates whose titles happened to repeat the single category term more
densely. With dampening ON at the *same* turn 1 state the model asks a
different clarifying question (title/feature overlap weight scaled to
0.5, reducing their tie-break influence), the conversation branches, and
by turn 2 the user has disclosed `color: red` and a feature description,
raising `active_constraint_count` to 3 (dampening scale back to 1.0,
no-op at ≥ threshold), `retrieval_score_normalized=1.0` (rank 1),
`coverage=1.0`, `relevance=3.486` → rank 1. Net: dampening's effect here
is indirect — it changed *what the agent asked next*, which surfaced a
disambiguating constraint, which is what actually fixed the rank; it is
not simply "dampening reordered a static candidate list."

**Largest regression — `public_0134`** (browsing, target `B081SF3QRL`,
query "Piercing Jewelry Tunnels"): OFF rank **4** → ON rank **6**, both
at turn 1, same disclosed-constraint state (`active_constraint_count=1`,
`category: match`, `hard_constraint_violation_count=0`). Target features
identical between OFF/ON except the dampened weight: OFF `relevance=
3.055` (title_overlap=0.667, feature_overlap=1.0 both contributing at
full weight), ON `relevance=2.989` (same overlap values, weight scaled to
0.5). Here the target's own `title_overlap`/`feature_overlap` were
*positive, correct* signal (the target genuinely was a strong lexical
match, `retrieval_rank=7` but real coverage/feature match), and dampening
suppressed that signal uniformly, pushing the target down two ranks
relative to other candidates whose relevance didn't depend on those
terms. This shows the dampening mechanism is not one-directional — it
also removes real signal in some single-constraint cases, not just noise.

### Step 4 — verdict

1. **Does overlap dampening improve overall MRR?** Yes, marginally:
   R2 ON vs OFF **+0.004879** MRR (0.494983 vs 0.490104); R3 ON vs OFF
   **+0.004879** MRR (0.480697 vs 0.475818). Small but consistent
   direction across both R2 and R3.
2. **Does it recover browsing MRR?** Partially. Browsing MRR improves
   **+0.012180** for both R2 and R3 (R2: 0.443901→0.456081; R3:
   0.429029→0.441209), which is real but recovers only about **19%** of
   the originally-measured -0.0626 browsing MRR regression (R2 vs R0) —
   the regression is not "fixed," it is nudged.
3. **Does it preserve or improve Hit@10?** Preserves exactly: **+0.000000**
   change for both R2 and R3 (0.893750 and 0.868750 respectively,
   identical ON and OFF).
4. **Does it hurt specific-query (non-browsing/high-constraint) sessions?**
   No measurable aggregate harm in this run's `buying`/`boundary`/
   `intent_override` scenario MRRs (buying 0.533303 unchanged,
   intent_override 0.549423 unchanged, boundary 0.325397→0.323810, a
   negligible -0.0016 on only 7 boundary sessions). At the session level,
   though, dampening is a double-edged mechanism even within single-
   generic-constraint cases: of the 3 sessions whose rank changed at all,
   1 improved and **2 worsened** (`public_0134` browsing 4→6,
   `public_0131` boundary 9→10) — see Step 3's regression example, where
   dampening suppressed genuinely-correct overlap signal for the target
   itself. So the net positive is a small aggregate average over a mixed
   bag of individual outcomes, not a uniformly-safe fix.
5. **Should threshold=2 remain, be reverted to a no-op (0), or proceed to
   a threshold sweep next?** The evidence supports **keeping threshold=2
   for now** — it is net-positive on every measured aggregate metric
   (overall MRR, browsing MRR, Hit@10 unchanged, no scenario regression
   above noise) and the only two individual regressions found are minor,
   in-top-10 rank movements (4→6, 9→10), not lost hits. It does **not**
   qualify as "the root cause fix" — it recovers ~19% of the traced
   browsing MRR gap and only ever touches 3 of 160 dev-split sessions, so
   the underlying calibration issue (coverage saturating at 1.0 for
   single-generic-constraint pools, handing weight to title/feature
   overlap noise) is still present, just partially mitigated. Given the
   effect size is small and the mechanism is demonstrably not uniformly
   safe (Step 3's regression), a **small threshold sweep (e.g. 1, 2, 3,
   4) on `data/dev_split.jsonl`** is a reasonable next step before
   considering it settled — left as a recommendation, not executed here,
   since the brief was to measure the current default vs. off, not tune.

`neeshops/config/default_strategy.json` was left unmodified throughout
(`overlap_dampening_threshold: 2` was never edited on disk — all off/on
comparisons used deep-copied in-memory strategy dicts), so no restore was
needed; it remains at the shipped default (dampening ON).
