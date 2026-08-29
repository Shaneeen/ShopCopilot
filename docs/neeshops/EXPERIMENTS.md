# Experiments log

Raw experiment output lives in `artifacts/experiments/` (gitignored — see
`neeshops/research/results_store.py`). This document is the human-curated
summary: what we tried, what we accepted into
`neeshops/config/default_strategy.json`, and why.

Keep entries short — one per accepted (or notably instructive rejected)
experiment. Generate the table below from `ResultsStore.all()` /
`ResultsStore.accepted()` rather than hand-maintaining metrics.

## Baseline

| Metric | Value |
|---|---|
| Hit Rate@10 | 0.125 |
| MRR | 0.068034 |
| MTTC | 9.81 |
| Technical Score | 0.10671 |

(Organiser's weak BM25 starter agent, `docs/baseline_results.json` — see
`docs/neeshops/COMPETITION_NOTES.md` for the reproduction steps.)

## Accepted experiments

_None yet — Stage 1 is architecture only. First real experiments land once
`evaluator/` is vendored and `scripts/setup_catalog.py` has been run
against the real catalog._

| ID | Hypothesis | Config change | Baseline → Candidate | Δ | Accepted |
|---|---|---|---|---|---|
| `candidate_initial` | Foundational NeeShops architecture (State, Clarification, BM25, Filters, Heuristic Ranking) outperforms stateless weak starter. | Full NeeShops pipeline over `default_strategy.json` | 0.10671 → 0.248074 | +0.141364 (+132.5%) | YES |

## Rejected experiments (instructive ones only)

| ID | Hypothesis | Why it failed |
|---|---|---|
| — | — | — |

## Guardrails

- Iterate against `data/dev_split.jsonl`, not the full 200-session public
  set — see `scripts/create_dev_split.py`. Check `data/holdout_split.jsonl`
  only occasionally, to catch overfitting before it shows up on the
  private 800-session set.
- Only parameters in `neeshops.research.experiment.SAFE_PARAMETERS` can be
  touched by an experiment. Extending that set is a deliberate code change,
  not something the optimizer does on its own.
- An experiment is accepted only if it beats baseline on the primary
  metric (`technical_score`) by at least `ExperimentRunner.min_improvement`
  — ties or noise-level gains should stay rejected.
