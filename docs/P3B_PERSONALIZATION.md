# P3B Personalisation

## Ownership and public API

Person 3B owns the local, soft personalisation signal and its evaluation. The existing 3A call remains unchanged:

```python
from neeshops.personalization.profile import personalization_boost

boost = personalization_boost(product_row, state.user_profile)
```

It returns a deterministic `float` in `[0, 1]`, performs no I/O, does not mutate inputs, and tolerates dictionaries, model objects, and missing fields. `explain_personalization(product_row, profile)` is an optional 3B debugging API; 3A does not need it.

## Scoring

Preference tags are deduplicated and normalised. Each tag is matched by presence, not frequency, against title (weight 1.0), categories (0.6), and description/features/details (0.3). Per-tag field evidence is divided by the total field weight, averaged across the unique profile tags, multiplied by profile confidence, then clamped.

Confidence is 0 for no tags, 0.35 for one tag, 0.70 for two or three tags, and 1.0 for four or more. This prevents sparse profiles from exerting full influence.

The concept map is intentionally small and interpretable. It covers only tags observed in the dev data: fit, material, comfort, style, durability, performance, warmth, and weather. Unknown tags use exact normalised phrase matching. Word boundaries prevent accidental substring matches, and repeated words never increase a field's contribution.

`rating_style`, `purchase_frequency`, and `average_prior_rating` are intentionally ignored. They describe user activity or rating behaviour but provide no defensible product-level affinity. They should only be added after held-out evaluation demonstrates value.

## Explicit constraints

Personalisation never filters or restores candidates. `NeeShopsAgent` applies explicit-constraint filters before invoking 3A's ranker, and the 3B hook sees only the resulting candidates. The existing low-retrieval-score preservation test remains in place. The integration weight remains owned by 3A; this branch does not change the default.

## Evaluation

Run:

```powershell
python scripts/evaluate_personalization_weights.py
```

The script runs the official evaluator over weights 0, 0.025, 0.05, 0.10, 0.15, 0.20, 0.30, and 0.40. It reports MRR, Hit@10, MTTC, MRR delta, improved/worsened/unchanged sessions, positive and harmful movement, personalisation regret, worst movement, top-1/3/10 preservation, and a fixed-seed bootstrap interval. It writes CSV, JSON, Markdown, reusable breakdowns, and top win/regression cases under `evaluation/results/`.

Breakdowns cover profile richness, observed baseline position, existing intent-card constraint richness, and sufficiently populated product categories. The official evaluator exposes only top-10 ranks; targets outside that window are clearly labelled “not retrieved in top 10,” and capped movement uses rank 11 without claiming it is the true full-candidate rank. Personalisation cannot recover a target absent from the candidate pool.

The script identifies a dev-set candidate weight, but it does not change 3A's configuration. Selection should consider MRR together with Hit@10, MTTC, preservation, regression count, regret, and bootstrap uncertainty. With only 160 dev sessions, small differences are not conclusive.

### Measured dev result

The completed 160-session sweep recommends **0.20 as a candidate for integration review**, not an automatic configuration change. It produced MRR 0.193492 versus the retrieval-order baseline 0.181796 (delta +0.011696), Hit@10 0.28125 versus 0.2625, and MTTC 8.5875 versus 8.73125. Twelve sessions improved, eight worsened, and 140 were unchanged under capped top-10 movement. Top-1, top-3, and top-10 preservation were 1.0, 0.9375, and 0.97619 respectively. The fixed-seed 95% bootstrap interval for MRR delta was [-0.000228, 0.026081], which crosses zero; the apparent gain is promising but not statistically definitive.

Weight 0.30 increased Hit@10 further but erased the MRR gain and caused larger regressions. Weight 0.40 materially reduced MRR. This supports a conservative 0.20 ceiling for further held-out review. Among profile-richness cuts, the one-tag group had the largest delta (+0.028571) but only five samples, so it should not be treated as the most reliable segment. The 2-3 tag group had the smallest positive delta (+0.008098). Baseline ranks 4-10 were the clearest weak segment (-0.014762), reinforcing the need to monitor regret.

## Failure modes and limitations

Tests cover empty/sparse/malformed profiles, missing product fields, unknown tags, repetition, duplicate tags, field strength, ignored weak statistics, deterministic bounds, no mutation, API compatibility, and constraint dominance.

The heuristic cannot understand concepts outside its conservative map, and a broad tag such as “material” is less precise than learned preference evidence. Offline cached embeddings remain a future experiment: they should be feature-flagged, benchmarked, optional at runtime, and adopted only if held-out gains justify their complexity. No embedding or learned-affinity experiment is included in the default path.
