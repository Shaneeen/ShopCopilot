# Experiments log

Raw experiment output lives in `artifacts/experiments/` (gitignored — see
`neeshops/research/results_store.py`). This document is the human-curated
summary: what we tried, what we accepted into
`neeshops/config/default_strategy.json`, and why.

Keep entries short — one per accepted (or notably instructive rejected)
experiment. Generate the table below from `ResultsStore.all()` /
`ResultsStore.accepted()` rather than hand-maintaining metrics.

## Organizer weak-starter reference (all 200 public sessions)

| Metric | Value |
|---|---|
| Hit Rate@10 | 0.125 |
| MRR | 0.068034 |
| MTTC | 9.81 |
| Technical Score | 0.10671 |

(Organiser's weak BM25 starter agent, `docs/baseline_results.json` — see
`docs/neeshops/COMPETITION_NOTES.md` for the reproduction steps.)

This table is a competition reference, **not** the comparison baseline for a
160-session development experiment. `scripts/run_experiment.py` first
measures the unchanged default NeeShops strategy on the exact `--dataset`,
then compares every candidate with that same-dataset result.

## Current NeeShops initial candidate (all 200 public sessions)

Measured 2026-08-28 with the official 50,000-product catalog, default
strategy, semantic retrieval disabled, and LLM reranking disabled:

| Metric | Value |
|---|---|
| Hit Rate@10 | 0.285 |
| MRR | 0.188581 |
| MTTC | 8.55 |
| Technical Score | 0.248074 |

This is evidence that the end-to-end candidate runs. It is not yet the
development-split baseline for the experiment table below.

## P3-D5: Ranking A/B — HeuristicRanker vs. identity/pass-through (160-session dev split)

Measured 2026-08-29 via `scripts/evaluate_ranking_ab.py` (`personalization_weight=0.15`,
`rerank_limit=50`) — both arms share one retrieval pass per session, so the
delta is attributable only to the ranking stage. Full per-sample_id
comparison saved to `artifacts/experiments/ranking_ab_1787938953.json`
(gitignored).

| Metric | Baseline (identity, no reranking) | Ranked (HeuristicRanker) | Δ |
|---|---|---|---|
| MRR | 0.181796 | 0.188373 | +0.006577 |
| Hit Rate@10 | 0.2625 | 0.2875 | +0.025 |

Per-scenario MRR (baseline → ranked): boundary 0.285714 → 0.285714,
browsing 0.144872 → 0.158333, buying 0.222282 → 0.224970,
intent_override 0.136364 → 0.136364 (unchanged — Intent Override sessions
are designed so the explicit-constraint override dominates regardless of
personalization).

## Accepted experiments

| ID | Hypothesis | Config change | Baseline → Candidate | Δ | Accepted |
|---|---|---|---|---|---|
| `candidate_initial` | Foundational NeeShops architecture (State, Clarification, BM25, Filters, Heuristic Ranking) outperforms stateless weak starter. | Full NeeShops pipeline over `default_strategy.json` | 0.106710 → 0.248074 | +0.141364 (+132.5%) | YES |
| `targeted::intent_override::personalization_weight=0.05` | Reducing personalization weight prevents past tags from fighting new intent. | `ranking.personalization_weight: 0.05` | 0.244890 → 0.245197 | +0.000307 (+0.1%) | YES |
| `targeted::intent_override::max_questions=3` | Allowing 3 questions gives the agent headroom to clarify multi-attribute requests and shifted intent. | `clarification.max_questions_per_session: 3` | 0.244890 → 0.286280 | +0.041390 (+16.9%) | YES |
| `targeted::intent_override::candidate_limit=300` | Expanding candidate limit to 300 ensures pivoted/strict queries retrieve products with higher recall. | `retrieval.candidate_limit: 300` | 0.286280 → 0.290780 | +0.004500 (+1.6%) | YES |
| `grid::clarification.max_questions=5` | Systematically sweeping question budgets (2→7) finds optimal multi-attribute constraint gathering. | `clarification.max_questions_per_session: 5` | 0.286280 → 0.332905 | +0.046625 (+16.3%) | YES |

## Rejected experiments (instructive ones only)

| ID | Hypothesis | Why it failed |
|---|---|---|
| `targeted::intent_override::ask_above=40` | Triggering clarification earlier when candidates > 40. | Tied baseline score (0.244890 → 0.244890). Rejected per strict delta > 0 guardrail. |
| `targeted::intent_override::personalization_weight=0.0` | Eliminating personalization completely to avoid bias on pivot. | Degraded performance (0.286280 → 0.276789, -3.3%). Personalization boost is critical for Buying/Browsing. |
| `targeted::intent_override::min_candidates=3` | Lowering candidate threshold before recommending to 3. | Tied baseline score (0.286280 → 0.286280). Rejected per strict delta > 0 guardrail. |
| `grid::retrieval.candidate_limit=400` | Expanding candidate retrieval pool to 400. | Sub-optimal (0.290577 vs 0.290780 for limit=300) with +11% latency overhead. |
| `grid::clarification.max_questions=6,7` | Testing question budget caps above 5. | Score plateaus at 0.332905 (available missing fields exhausted in rule-based engine). |

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
  — ties stay rejected even when the configured minimum is zero, and
  noise-level gains should use a positive minimum.
