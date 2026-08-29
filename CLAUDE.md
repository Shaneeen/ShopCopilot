# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two layers, kept strictly separate:

1. **The organiser's official participant kit** (`evaluator/`, `starter/agent.py` shape, `docs/*.md` at repo root, `data/public_set.jsonl`) — vendored from `TechJam2026/techjam-conversational-search`, **never modify**. It defines the Agent contract (`docs/agent_api_contract.json`) and scores submissions on Hit Rate@10 / MRR / MTTC.
2. **NeeShops** (`neeshops/`) — our team's implementation, layered on top via `starter/agent.py` as a thin adapter. `README.md` "NeeShops implementation" section is the canonical overview; everything below is a condensed map for fast orientation, not a replacement for it.

## Commands

```bash
# Setup
python -m pip install -r requirements.txt
python scripts/download_catalog.py   # official catalog + checksum + 50k-row validation
python scripts/check_readiness.py    # explains any missing setup item, run this first when confused
python scripts/setup_catalog.py      # builds the BM25 SQLite FTS5 index (data/catalog.fts.db)
python scripts/create_dev_split.py   # writes data/dev_split.jsonl (160) / data/holdout_split.jsonl (40)

# Tests
pytest                                       # everything (official evaluator tests + ours)
pytest tests/test_ranking.py                 # one file
pytest tests/test_ranking.py::test_personalization_never_overrides_explicit_low_retrieval_score  # one test

# Evaluation
python3 -m evaluator.local_evaluator         # official evaluator, writes results.json (uses data/public_set.jsonl)
python scripts/run_baseline.py               # fast adapter smoke check, no full evaluator
python scripts/evaluate.py [--dataset data/public_set.jsonl]   # official evaluator + archives metrics to artifacts/experiments/
python scripts/run_experiment.py --grid retrieval.browsing.semantic_weight 0.3 0.5 0.7
python scripts/run_experiment.py --random 3  # measures default-strategy baseline on --dataset, then each candidate
python scripts/evaluate_ranking_ab.py        # HeuristicRanker vs. identity/no-reranking A/B, reports MRR delta (P3-D5)
```

All of these expect `data/catalog.jsonl` installed and, for the split/experiment scripts, `scripts/create_dev_split.py` already run. `scripts/check_readiness.py` diagnoses which of these is missing rather than guessing.

## Architecture

Request flow (see `docs/neeshops/ARCHITECTURE.md` for the full diagram):

```
evaluator/ (official) → starter/agent.py (frozen adapter shape)
    → neeshops/agent.py: NeeShopsAgent (orchestration only, no logic of its own)
        → neeshops/conversation/  (state, buying/browsing intent routing, constraint extraction, ask-vs-recommend decision)
        → neeshops/retrieval/     (BM25 [working] + semantic [stub] → metadata filters → hybrid weighted merge)
        → neeshops/ranking/       (HeuristicRanker [working]: retrieval score blended with personalization boost;
                                    LLMReranker [stub, feature-flagged])
        → neeshops/personalization/ (soft profile → ranking boost; never a hard filter — explicit constraints always win)
```

- `starter/agent.py` is the **only file the official evaluator imports**; it must keep its exact constructor/`reset`/`respond` shape (`docs/agent_api_contract.json`, `additionalProperties: false`) and stay ~30 lines — any real logic added there is a bug.
- Every tunable weight (retrieval blend, `ranking.rerank_limit`, `ranking.personalization_weight`, clarification thresholds) lives in `neeshops/config/default_strategy.json`, read via `neeshops/config/settings.py`. Nothing else hardcodes a weight.
- `neeshops/research/` is a controlled experimentation framework: an `Experiment` may only touch parameters in `SAFE_PARAMETERS`, `ExperimentRunner` runs it through a supplied `evaluate_fn` (wired to the real evaluator in `scripts/run_experiment.py`) and accepts/rejects on the `technical_score` delta, `ResultsStore` appends history to gitignored `artifacts/experiments/`. It never imports `evaluator/` directly.
- Retrieval candidates arrive from `HybridRetriever` **already sorted best-first** by score (`neeshops/retrieval/candidate_merge.py`) — a ranker that just truncates that list *is* the identity/no-reranking baseline (see `scripts/evaluate_ranking_ab.py`'s `IdentityRanker`).
- `docs/neeshops/FOLDER_GUIDE.md` has a per-module table (owner, interfaces, inputs/outputs, TODOs, which tests to run after touching it) — check it before exploring a module blind.
- `docs/neeshops/INTEGRATION_CONTRACTS.md` is the source of truth for every cross-module interface signature (exact method names/types/failure behaviour); update it in the same PR as any signature change.

## Team ownership boundaries

Six workstreams, each owning a folder to minimise merge conflicts (`docs/neeshops/TEAM_WORKSTREAMS.md`); Person 3 is split into **3A (Ranking Core, `neeshops/ranking/`)** and **3B (Personalisation & Evaluation, `neeshops/personalization/`, `scripts/evaluate*.py`, `scripts/run_experiment.py`)** — their division of labor, shared integration seam (`personalization_boost()` hook called by `HeuristicRanker`), and git workflow are in `HOW_A_AND_B_WORK_TOGETHER.md`. A ranker (3A) must fall back to `HeuristicRanker` rather than raising or returning empty results if `LLMReranker` is unavailable.

Current branch (`shaneen/person-3b-personalization`) is Person 3B's workstream — avoid modifying `neeshops/retrieval/`, `neeshops/conversation/`, `neeshops/ranking/` (except the personalization hook), `starter/agent.py`, or `evaluator/` from here; coordinate via `docs/neeshops/INTEGRATION_CONTRACTS.md` instead.

## Hard requirements worth knowing before touching ranking/personalization

- Personalisation is a **soft** signal only — an explicit user constraint (category, budget, etc.) must never be outranked by a personalization-boosted item that violates it (Track 4 requirement 7; enforced by `tests/test_ranking.py::test_personalization_never_overrides_explicit_low_retrieval_score`).
- No fabricated numeric confidence in a recommendation's `reason` string — human-readable text only (`docs/neeshops/COMPETITION_NOTES.md`).
- `data/public_set.jsonl` is the 200-session labeled set; **iterate against `data/dev_split.jsonl` (160 sessions)**, not the full public set, and check `data/holdout_split.jsonl` only occasionally to catch overfitting (`docs/neeshops/EXPERIMENTS.md` guardrails). Never touch `data/public_set.jsonl` itself.
- `data/catalog.jsonl`, `data/*.fts.db`, `data/dev_split.jsonl`, `data/holdout_split.jsonl`, and `artifacts/` are all gitignored/generated — regenerate via the setup commands above rather than expecting them to be present after a fresh clone.
