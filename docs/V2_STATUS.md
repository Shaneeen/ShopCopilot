# v2 Status — What Was Accomplished & What's Still Open

Date: 2026-08-30 · Branch state: single working tree on the v2 restructure ·
Companion doc: `docs/IMPLEMENTATION_V2.md` (as-built decision log).

## Scorecard (official evaluator, 200 public sessions)

| Metric | v1 baseline | **v2 now** | Δ |
|---|---|---|---|
| Hit@10 | 0.805 | **0.870** | +6.5pp |
| MRR | 0.402 | **0.4455** | +4.4pp |
| MTTC | 3.93 | **3.465** | −0.47 |
| TechnicalScore | 0.665 | **0.7193** | +5.4pp |
| buying / browsing / override / boundary | 0.913 / 0.725 / 0.800 / 0.600 | **0.875 / 0.900 / 0.800 / 0.800** | −3.8 / +17.5 / = / +20 pp |

Tests: **248 passed, 1 deselected** (was 162). Conservative targets from the plan:
Hit ≥ 0.87 ✅ · MRR ≥ 0.44 ✅ · MTTC ≤ 3.2 ❌ (3.47) · Tech ~0.72 ✅ (to rounding).

## Accomplished

- **Exact-recall guarantee pool** (`retrieval/token_index.py`): in-memory Boolean
  inverted index (50k docs / 95.5k terms, 3.5 s build, one per catalog), greedy
  token-group backoff, price-gated with fail-open, popularity table, coverage
  primitives. Front-loaded into the 200-pool; over-generality regime fills the pool
  with corroborated-then-popular AND members.
- **Ranking v2**: coverage×IDF×salience features, `(violations, −coverage, −relevance,
  −popularity, asin)` sort, minmax retrieval normalization, browsing popularity bump,
  inferred-attribute bonuses (never filters).
- **Clarification v2**: 8 ordered gates (turn-guard at 9, confident-stop, wildcard ×2
  with compound harvest, over-generality → set-splitting entropy over the stride-
  sampled plausible AND set, agreement → inferred slots), answerability-correct askable
  fields (brand/category excluded), catch-all drain chain.
- **State lifecycle**: per-value contradiction staling (weight 0.3, re-affirmation
  recovery), decaying inferred slots, override-safe semantics matched to the harness.
- **Extraction fixes that paid**: category capture stops at commas (+14.5pp Hit),
  same-field compound merge reconstructs multi-part card values, no mid-word
  truncation, route detection on raw tokens.
- **Fast filters**: O(1) token-set membership (was: full-text rescan per candidate
  per turn).
- **Gated LLM tier** built (twins/margin gates + ε-blend) — default OFF.
- **Tooling**: instrumented panel + miss decomposition, pool-miss forensics
  (94.7% clean at n=300; rest self-heals via backoff), pseudo-attribute miner +
  pruned sidecar, `--arms`/`--workers` bench flags, SAFE_PARAMETERS full registration
  + config guard test.

## Main issues still open (ranked)

1. **Bench v1 gate unmeasured** (insane ≥ 0.50 target). Wall-time bound: the full
   100-case × 2-arm bench exceeds every 10-minute execution cap in this environment.
   Root causes found & fixed: per-case agent rebuilds re-parsing the 50k catalog
   (cached now), GIL thrashing at `--workers 8` (use `--workers 1` — threads give no
   parallelism for CPU-bound Python), pseudo-attribute evidence re-tokenizing rows
   (cached now). Remaining: ~1.5–2.5 min/arm expected — run
   `python scripts/bench_v1.py --cases 100 --workers 1 --arms no-llm` and
   `--arms fake-llm` separately, on a machine/session without the cap.
2. **Buying still −3.8pp vs baseline** (0.875 vs 0.913). Miss class: rank misses —
   target in the 200-pool but crowded out of the top-10 among ~200 full-coverage
   AND members where popularity/relevance decide. Candidate levers (unmeasured):
   salience-weighted AND-member ordering, per-route rerank windows, more aggressive
   AND narrowing (4th question is already enabled and worth +0.5pp).
3. **MTTC 3.465 vs ≤3.2 target**. Question budget (avg 2.3–2.5 asks) buys Hit at
   Efficiency's expense; the turn-guard at 9 is correct but sessions rarely get there.
   Would need gate re-tuning (`margin_stop`, `other_max_asks`) against the
   Hit/MTTC frontier — grid it before submission.
4. **Latency p50 ~230 ms vs the 150 ms goal** (no scored metric depends on it).
   Dominated by 3 semantic matrix dots per turn + entropy regex passes. The pseudo-
   attribute/corpus caches already removed the worst spikes (798 ms → ~360 ms).
5. **P5 LLM re-test not run** (needs OpenRouter credits + wall time). Everything is
   built and default-off; runbook in `docs/IMPLEMENTATION_V2.md §6`. Ship/kill:
   ΔHit ≥ +0.03 AND ΔMRR ≥ +0.02 AND trigger ≤ 30% AND added p95 ≤ 2s.
6. **Over-generality is the normal regime** (AND > 200 in ~195/200 sessions; pool
   membership ~84% of scored turns). The guarantee tier is exact only once the AND
   set drops ≤ 200 — i.e. after 2–3 harvested values. Structural: the residual
   misses are the `rank` class, not `pool`.
7. **Evaluator-side truncation** (frozen file): 180-char card values cut mid-word in
   ~5% of sessions; harmless to recall (backoff drops the junk token) but it forfeits
   that value's full narrowing power. Not fixable without touching `evaluator/`.
8. **Housekeeping**: token-index memory not measured (estimate ~60–100 MB — within
   the in-memory rule); `SAFE_PARAMETERS` now admits every shipped key (the
   experiment allowlist is permissive — deliberate, but review before open-ended
   sweeps); `p50` panel latency includes first-session warm-up (caches).

## Suggested next session order

1. Bench arms (2 runs, `--workers 1`) → record insane gate.
2. Grid `margin_stop` {0.10, 0.15, 0.20} × `other_max_asks` {1, 2} on the public set
   → pick the Hit/MTTC frontier point.
3. P5 re-test per runbook → ship/kill decision.
4. Buying rank-miss forensics from `instrumented_results.json` (the 8 sessions).
