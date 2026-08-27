# `neeshops/research/`

**Owner/workstream**: Person 4 — Research Agent, Evaluation &
Experimentation (see `docs/neeshops/TEAM_WORKSTREAMS.md`).

## Purpose

A controlled, evaluator-backed experimentation loop over a declared-safe
parameter allowlist. **Never rewrites application code** — an experiment
is a named diff against `neeshops/config/default_strategy.json`, nothing
more.

## Public interfaces

```python
class Experiment:
    name: str; hypothesis: str; parameters: dict[str, float]; experiment_id: str
    def build_strategy(self, base=None) -> dict: ...
    # raises ValueError if any parameter key isn't in SAFE_PARAMETERS

SAFE_PARAMETERS: set[str]  # the only dot-paths an Experiment may touch

class ExperimentRunner:
    def __init__(self, evaluate_fn: (dict, str) -> dict[str, float],
                 results_store=None, min_improvement=0.0): ...
    def run(self, experiment, dataset_path, baseline_metrics, base_strategy=None) -> dict

class ResultsStore:
    def record(...) -> dict
    def all(self) -> list[dict]
    def accepted(self) -> list[dict]

propose_grid(param_path, values) -> list[Experiment]
propose_random(search_space=None, n=5, seed=None) -> list[Experiment]
next_experiments(scenario_metrics) -> list[Experiment]  # currently == propose_random(n=3)
```

Wired to the real evaluator by `scripts/run_experiment.py` — `neeshops/research/`
itself has zero import dependency on `evaluator/`, so it's testable without
the evaluator or catalog present (see `tests/test_research.py`).

## Current implementation

`ExperimentRunner.run()` builds a strategy from the experiment's overrides,
calls the supplied `evaluate_fn`, compares `PRIMARY_METRIC =
"technical_score"` against `baseline_metrics`, and accepts iff the
candidate beats baseline by at least `min_improvement` (default 0). Every
run — accepted or rejected — is appended to
`artifacts/experiments/results.jsonl` (gitignored).
`scripts/run_experiment.py` aliases the official evaluator's
`recommended_technical_score` key to `technical_score` so this stays
metric-name-agnostic.

## How to extend

`optimizer.next_experiments()` is a random-search placeholder — it doesn't
look at `scenario_metrics` yet. The intended upgrade: inspect
`evaluate()`'s `scenario_metrics` (buying/browsing/intent_override/
boundary breakdown), find the weakest scenario, and target a parameter
likely to help that scenario specifically (e.g. weak Browsing Hit Rate@10
→ propose raising `retrieval.browsing.semantic_weight`). Add new tunables
to `SAFE_PARAMETERS` deliberately — it's an allowlist by design.

## How to test

```bash
pytest tests/test_research.py
```

To actually run an experiment against real data (once the catalog is
installed):

```bash
python scripts/create_dev_split.py
python scripts/run_experiment.py --grid retrieval.browsing.semantic_weight 0.3 0.5 0.7 0.9
```

## Known TODOs

- No experiment has actually been run against real data in this
  environment — `docs/neeshops/EXPERIMENTS.md` is empty by design, not
  oversight.
- `next_experiments()` doesn't yet target weak scenarios.
- No internal dev/holdout generalisation check has been run yet
  (`scripts/create_dev_split.py` exists but hasn't been exercised against
  real data here).
