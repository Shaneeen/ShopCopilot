# Person 3B — Personalisation & Evaluation

Welcome to the Personalisation & Evaluation workstream! This document details the responsibilities, code ownership, interfaces, and deliverables for Person 3B.

## Workstream Overview

As Person 3B, you are responsible for translating aggregate user profile signals into soft ranking adjustments, ensuring that explicit shopper constraints are respected, and evaluating how ranking changes affect search quality metrics (such as MRR and Hit Rate@10).

### Key Files and Directories
- **Personalisation Logic**: [`neeshops/personalization/profile.py`](file:///c:/Users/popla/OneDrive/Desktop/ShopCopilot/neeshops/personalization/profile.py)
- **Tuning Config**: `ranking.personalization_weight` (default 0.15) in [`neeshops/config/default_strategy.json`](file:///c:/Users/popla/OneDrive/Desktop/ShopCopilot/neeshops/config/default_strategy.json)
- **Personalisation Unit Tests**: [`tests/test_ranking.py`](file:///c:/Users/popla/OneDrive/Desktop/ShopCopilot/tests/test_ranking.py) (specifically constraint-override behavior)
- **Evaluation Entrypoints**: [`scripts/evaluate.py`](file:///c:/Users/popla/OneDrive/Desktop/ShopCopilot/scripts/evaluate.py) and [`scripts/run_experiment.py`](file:///c:/Users/popla/OneDrive/Desktop/ShopCopilot/scripts/run_experiment.py)

---

## Deliverables & Acceptance Criteria

### P3-D2: Soft Personalisation
- **Description**: Convert the aggregate user profile from the conversation state into a soft ranking boost.
- **Rules**:
  1. The personalization boost must act as a soft signal (default weight: `0.15` in `default_strategy.json`).
  2. Explicit user constraints (e.g. category, budget) must take priority. A product that violates explicit constraints must not be boosted above a product matching them.
- **Verification**: Run `pytest tests/test_ranking.py::test_personalization_never_overrides_explicit_low_retrieval_score`.

### P3-D5: Ranking Evaluation
- **Description**: Compare the ranking strategy against retrieval-only order to measure the exact MRR delta.
- **Process**:
  1. Coordinate with Person 4 (Research/Evaluation) to set up and run experiments.
  2. Use A/B style evaluations (comparing `HeuristicRanker` vs. an identity/pass-through ranker) using `scripts/run_experiment.py`.
  3. Ensure no performance improvement claims are made without a corresponding evaluator run log in `docs/neeshops/EXPERIMENTS.md`.

---

## Technical Guides

### How Personalisation Works
Personalisation is applied per candidate row via `neeshops.personalization.profile.personalization_boost(product_row, user_profile)`:
```python
def personalization_boost(product_row: dict[str, Any], profile: UserProfile) -> float:
    # Matches tags in user_profile against product_row categories or details
    # Returns a float boost in [0.0, 1.0]
```
The boost is scaled by `ranking.personalization_weight` and added to the candidate's score inside `HeuristicRanker`.

### How to Run Evaluation
To run a local baseline check and obtain metrics:
```bash
python scripts/run_baseline.py
```
To run an experiment tracking personalization weights:
```bash
python scripts/run_experiment.py --random 3
```
Check results and MRR deltas in the console output and record accepted configurations.
