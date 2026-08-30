# How Person 3A and Person 3B Work Together

This document outlines the collaboration boundaries, file ownership, integration points, and branch synchronization rules for **Person 3A (Ranking Core)** and **Person 3B (Personalisation & Evaluation)** under the split of the Person 3 role.

## 1. Division of Labor & File Ownership

To avoid merge conflicts, we divide file and module ownership as follows:

| Component | Responsibility / Owner | Main Files |
|---|---|---|
| **Ranking Core (3A)** | Reranking logic, LLM integration, fallbacks, timeout handling | `docs/person 3/3A_RANKING_CORE.md`, `neeshops/ranking/` (except personalization hooks), `neeshops/ranking/llm_reranker.py`, `neeshops/ranking/heuristic.py` |
| **Personalisation & Evaluation (3B)** | Soft profile personalization signals, evaluation metrics and A/B experiments | `docs/person 3/3B_PERSONALIZATION_EVAL.md`, `neeshops/personalization/`, `neeshops/personalization/profile.py`, `scripts/evaluate.py`, `scripts/run_experiment.py` |

---

## 2. Shared Integration Seams

### The Personalisation Boost Hook
- **Logic**: `HeuristicRanker` (maintained by 3A) calls `personalization_boost` (maintained by 3B) for each candidate.
- **Contract**: Any changes to `personalization_boost` signature must be additive (e.g., using default-valued keyword arguments) and documented in `docs/neeshops/INTEGRATION_CONTRACTS.md`.
- **Weighting**: The weight for personalization is read from `default_strategy.json` (`ranking.personalization_weight`) so that no numeric weights are hardcoded.

### Fallback & Orchestration
- If 3A's `LLMReranker` fails or is disabled, the pipeline must fall back to 3B's personalization-boosted `HeuristicRanker` rather than raising an error or returning empty results.

---

## 3. Git Workflow & Synchronization

Both developers base their work on the local-only `Shaneen` branch:

### Setup Branches
```bash
# Person A
git switch Shaneen
git switch -c shaneen/person-3a-ranking

# Person B
git switch Shaneen
git switch -c shaneen/person-3b-personalization
```

### Development & Commits
- Make small, focused commits prefixed with `docs(person-3a):` or `docs(person-3b):` respectively.
- Only modify files under your direct ownership. For shared files (like `README.md`, `CHANGELOG.md`, and this file), coordinate edits or merge carefully.

### Merging back to Shaneen
When ready, merge both branches into `Shaneen` using `--no-ff` (no fast-forward) to preserve history, then push:
```bash
git switch Shaneen
git merge --no-ff shaneen/person-3a-ranking
git merge --no-ff shaneen/person-3b-personalization
git push -u origin Shaneen
```
