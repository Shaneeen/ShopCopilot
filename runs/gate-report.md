# Gate Report — question-margin (exp/question-margin)

**Date:** 2026-08-30
**Dataset:** data/dev_split.jsonl (160 sessions, dev-160)
**Commit:** 80eee9a
**Panel:** Hit@10 0.881, MRR 0.443, MTTC 3.319 (instrumented_eval — dev-160)

## Question

> In the late phase (candidate set ≤ rerank floor = 40), does the last question before a miss collapse the candidate set size without improving top-10 margin, wasting a turn?

## Method

Extended `scripts/instrumented_eval.py` to profile every **missed** session's **LAST question**:

- **(a) Percent reduction in candidate-set size** — `(before AND - after AND)/before AND *100` (fallback to `pool_size` if AND unavailable). `before` = turn where `ask_attribute` was issued, `after` = next turn after the user's answer is applied (preview-state pipeline, so effect is visible on the next turn).
- **(b) Change in top-10 margin** — two measures:
  - `margin = score_rank1 - score_rank2` where score = `ConstraintAwareRanker._ordering_score` (exposed via `response["recommendations"][i].score`).
  - `rel_margin = relevance_rank1 - relevance_rank2` from `ranker.last_diagnostics[].relevance_score` (finer, since ordering_score compresses to `0` / `-1` tiers when violations tie, producing `margin=0` for 18/19 misses).

Late phase defined as `before_and ≤ rerank_floor (40)` else `before_pool ≤40`.

Thresholds for pattern "large set collapse, flat/negative margin":
- Large collapse ≥30% (loose check ≥20%)
- Flat margin `rel_margin_delta ≤0.02` and `margin_delta ≤0.01`; negative check `≤0`.

## Results (dev-160, 19 misses)

- Total misses: 19 (miss decomposition: pool 2, rank 13, extraction 1, override 3)
- Misses with a last question: 19/19 (100%)
- Measurable (before→after exists): 19/19
- **Large collapse ≥30%: 0/19 (0%)** — every last question achieved `pct_reduction = 0.0%` (both AND and pool: `before==after` for all 19, e.g., 623→623, 4111→4111, 50000→50000)
- Flat margin (ordering) ≤0.01: 19/19 (100%) but vacuously (margin was 0→0 for 18/19)
- Flat relevance margin ≤0.02: mix of small +/− (−0.15 to +0.04), but irrelevant since pct never ≥30%
- **Pattern large-collapse + flat margin (≥30% & ≤0.01): 0/19 = 0.0%** (also 0% with looser ≥20% & ≤0.02, 0% with negative ≤0, 0% with relevance metric)
- **Late-phase measurable: 0/19** — no miss had `before_and ≤40` (observed before_and 159–50000, mean final AND 3938, over-generality in 155/160 sessions). `late_pattern` = 0.

Per-miss last-question dump (all pct 0.0%):
public_0112 color 623→623 0.0% rel +0.021 late False; 0003 style 652→652 0.0% rel −0.051; 0171 style 159→159 0.0%; 0004 color 4189→4189 0.0% rel +0.003; etc. (full rows in `evaluation/results/instrumented_results.json:gate_profile.rows`)

The only large collapses occur **earlier** (e.g., public_0112 turn 4→5: 4121→623 = 84.9% on the *penultimate* question), not on the last question. The last question is uniformly ineffective at shrinking the AND set; it also does not move ordering margin (already 0) and moves relevance margin only ±0.02 on average.

## Gate Decision

**FAIL / STOP.** Pattern fraction 0% < 1/3 threshold. The hypothesized mechanism — late-phase questions that collapse set size without changing ranking — is not observed:

1. Late phase (≤40) is never reached on dev-160 (0/19 late), so the premise is vacuous under current `plausible_set_limit=200` / `rerank_floor=40` operating point.
2. Even ignoring the late-phase filter, the last question never achieves a large set collapse, so no turn is wasted by "collapsing without ranking."

## Recommendation

Do not build a late-phase margin-gain question value. A clean negative result — gate does not pass. Next win is likely elsewhere (MTTC frontier `margin_stop × other_max_asks`, partial pool window, or retrieval-ranking balance), not a late-phase entropy→margin switch.

---
*Instrumented run saved to `evaluation/results/instrumented_results.json` (panel + gate_profile). Reproduce: `python scripts/instrumented_eval.py --dataset data/dev_split.jsonl`*
