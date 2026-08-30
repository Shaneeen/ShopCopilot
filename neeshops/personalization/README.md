# Personalisation

Person 3B owns the soft user-profile signal and its evaluation. Profile data
is never a filter and never outranks explicit constraints. The official
profile enters through `Agent.reset()`, is stored in `ConversationState`, and
is converted to a bounded `[0, 1]` feature by `personalization_boost()`.

## Production integration

The deployed `ConstraintAwareRanker` reads the feature through
`RankingFeatureExtractor`. Its active weight is
`ranking.deterministic.weights.personalization` in
`neeshops/config/default_strategy.json`. It defaults to `0.0`/disabled after
the current-ranker evaluation found no Hit@10 gain and a small negative MRR
delta at `0.03`. The top-level
`ranking.personalization_weight` remains for compatibility with the legacy
heuristic and optional LLM paths; evaluation helpers synchronize both keys.

Explicit hard-constraint violations are the ranker's first ordering key, so
personalisation can move otherwise close candidates but cannot rescue a
product that violates a stated brand, colour, material, size, category, or
budget requirement.

## Verification

Run the focused tests:

```bash
.venv/bin/python -m pytest -q tests/personalization tests/test_ranking.py tests/test_deterministic_ranking.py
```

Run P3-D5 against the current production ranker:

```bash
.venv/bin/python scripts/evaluate_ranking_ab.py
```

To reproduce the evaluated non-zero candidate:

```bash
.venv/bin/python scripts/evaluate_ranking_ab.py --personalization-weight 0.03
```

The script reports three arms:

1. retrieval order only;
2. `ConstraintAwareRanker` with personalisation disabled;
3. the same ranker with personalisation enabled.

The difference between arms 2 and 3 is the personalisation-only delta. This
is the Person 3B acceptance number. The difference between arms 1 and 2 is
the wider Person 3A ranking-stage delta.

Both evaluation entrypoints relaunch themselves with `PYTHONHASHSEED=0` and
run every arm in a fresh spawned interpreter. This stabilizes set-backed
candidate ordering and prevents process-level V2 caches warmed by one arm
from contaminating the next arm.

For a weight sweep using the same-ranker baseline:

```bash
.venv/bin/python scripts/evaluate_personalization_weights.py
```

Committed summaries live under `evaluation/results/`; timestamped detailed
P3-D5 artifacts live under ignored `artifacts/experiments/`.

## Interactive demo

Start `.venv/bin/python scripts/interactive_demo.py`, enter comma-separated
profile tags in the header, and click **New session**. The selected tags are
sent to `/api/reset`, making the real personalisation path testable instead
of silently using an empty profile. To observe rank movement, enable a non-
zero deterministic personalisation weight in a local strategy experiment.

## Accepted P3-D5 result

Dataset: `data/dev_split.jsonl`, 160 sessions, production rerank window 40.

- Retrieval-only: MRR `0.502056`, Hit@10 `0.875000`.
- Current ranker, profile off: MRR `0.490104`, Hit@10 `0.893750`.
- Current ranker at weight `0.03`: MRR `0.489010`, Hit@10 `0.893750`.
- Personalisation-only delta: MRR `-0.001094`, Hit@10 `0.000000`.
- Bootstrap 95% CI for the MRR delta: `[-0.010231, 0.008229]`.

Conclusion: the effect is statistically inconclusive and does not improve
Hit@10. The safe production choice is weight `0.0`; retain the feature for a
future profile-specific dataset or broader weight sweep.
