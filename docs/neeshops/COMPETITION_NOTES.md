# Competition notes

## Context

**TechJam 2026 — Shopping Copilot: AI Conversational Search and
Recommendations.** Official repo: `TechJam2026/techjam-conversational-search`.

Organiser provides:
- Frozen 50,000-product `Clothing_Shoes_and_Jewelry` catalog
- 200 labelled public dev sessions
- 800 hidden private eval sessions
- A weak BM25 starter agent
- A deterministic local evaluator
- The Agent API contract
- Baseline results & eval config

**Do not modify the official evaluator to artificially improve results.**

## Baseline Acceptance Test

The official evaluator is vendored under `evaluator/`. The original starter
was replaced by a thin adapter into NeeShops. The current Agent adds state,
clarification, score normalization, filtering, ranking, and personalisation,
so it is **not** an exact reproduction harness for the original stateless,
field-weighted BM25 starter. Keep these two starting points separate:

- organizer weak-starter reference: reproduce from a clean checkout/tag of
  the official participant repository;
- NeeShops initial candidate: run this repository's current Agent.

Before tuning begins, confirm all four hold:

1. Catalog installed: `data/catalog.jsonl` exists (see `data/README.md` —
   download from the GitHub Release, not committed).
2. Adapter imports and runs: `python scripts/run_baseline.py` completes
   without error and returns non-empty recommendations.
3. Evaluator completes: `python3 -m evaluator.local_evaluator` runs to
   completion and writes `results.json`.
4. The clean official starter is approximately:

   ```text
   Hit Rate@10   0.125
   MRR           0.068034
   MTTC          9.81
   Technical Score 0.10671
   ```

### How a teammate reproduces this

```bash
git clone <this repo> && cd <this repo>
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/download_catalog.py
python scripts/check_readiness.py

python scripts/create_dev_split.py     # our deterministic 80/20 dev/holdout split
pytest                                 # official tests/test_evaluator.py + our supplementary tests
python scripts/run_baseline.py         # fast smoke check of the adapter
python3 -m evaluator.local_evaluator   # full official evaluation, per the official README
```

If the **clean upstream starter** differs meaningfully from the published
baseline, investigate environment/data differences and never modify the
evaluator. A NeeShops score difference is expected because it is a different
Agent; record it as a separate candidate with its exact dataset and strategy.

## Avoiding public-set overfitting

The public set is only 200 labelled sessions; the private set is 800
unseen ones. `scripts/create_dev_split.py` makes a deterministic 160/40
(80/20) internal split so day-to-day experiment iteration happens against
`data/dev_split.jsonl`, with `data/holdout_split.jsonl` checked only
occasionally as an early warning for overfitting. Never tune every
experiment against all 200 labelled sessions — see
`docs/neeshops/EXPERIMENTS.md` → Guardrails.

## Recommendation reasons: no fabricated confidence

Recommendation `reason` strings (see `neeshops/ranking/heuristic.py`) must
stay human-readable characterizations ("best match", "strong value",
"closest to your style") — never an invented numeric confidence score
presented as if it were measured. The internal `score` used for ordering
is real (retrieval + personalization blend); it is not the same thing as a
calibrated confidence, and should not be surfaced to the frontend as one.

## Research agent scope

The research agent (`neeshops/research/`) is a controlled experimentation
loop over a declared allowlist of config parameters
(`neeshops.research.experiment.SAFE_PARAMETERS`) — it evaluates candidate
strategy configs and accepts/rejects them based on measured improvement.
It is explicitly **not** an autonomous agent that rewrites application
code. Do not extend it to modify source files.
