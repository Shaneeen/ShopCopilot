# Handover — Rebuild ShopCopilot From Scratch (2026-08-31, freeze 46e3322)

For the next human + AI. Everything needed to rewrite the scripts, rebuild the deck, and know what was tried in Round 1 vs Round 2.

## 0. Where to start
1. `docs/V3.md` — single technical handover (architecture, simulator, what shipped, levers, reproduce).
2. `docs/experiment-ledger.md` — metrics matrix + run inventory + ledger + gaps (tables, not prose).
3. `docs/HANDOVER.md` (this file) — rounds mapped to hypotheses, rebuild kit for deck/script/report.
4. `README.md` — frozen scores + quickstart.
5. `AGENTS.md` — experiment rules (dev-160 only, paired flips, SAFE_PARAMETERS, pytest 332).

## 1. What this is (30s)
TikTok TechJam 2026 Track 4. Headless agent, 10 turns max, top_k=10, 50k Clothing_Shoes_and_Jewelry catalog. 200 public sessions, 800 hidden (40/40/15/5 buying/browsing/override/boundary). Starter BM25: Hit 0.125, MRR 0.068, MTTC 9.81, Tech 0.1067. Tech=0.5*Hit+0.3*MRR+0.2*clip((11-MTTC)/10).
Thesis: maximize information per turn via exact uncertainty (TokenIndex AND size) → set-splitting questions, not better retrieval alone.

## 2. Repo map (after cleanup)
```
ShopCopilot/                      # canonical repo, branch staging-main @46e3322, tags fork-point/new-baseline/submission-freeze
  evaluator/local_evaluator.py    # frozen, never edit
  starter/agent.py                # ~80-line adapter, delegates to neeshops/
  neeshops/ agent.py conversation/ retrieval/ ranking/ personalization/ research/ config/default_strategy.json
  scripts/ instrumented_eval.py bench_v1.py pool_miss_forensics.py setup_catalog.py build_semantic_index.py create_dev_split.py interactive_demo.py presentation/build_deck.js
  data/ catalog.jsonl catalog.fts.db semantic.index.npy dev_split.jsonl(160) holdout_split.jsonl(40) public_set.jsonl(200)  # gitignored, built locally
  runs/ control-dev-newbaseline.json(160/144 authoritative) dev-*.json + archive/ (branch-only JSONs/md preserved after cleanup)
  docs/ V3.md HANDOVER.md experiment-ledger.md PRESENTATION.md SPEAKER_SCRIPT.md VIDEO_SCRIPT.md REPORT.md final-eval-record.md presentation/ShopCopilot_TechJam_Deck.pptx/.pdf
  tests/ 332 passed,1 deselected
Parent sc-*/ worktrees removed after archiving; see §7.
```

## 3. Reproduce (copy-paste, Windows PowerShell)
```powershell
pip install -r requirements.txt
python scripts/setup_catalog.py          # builds data/catalog.fts.db 92MB
python scripts/build_semantic_index.py   # if semantic.index.npy missing
python scripts/create_dev_split.py       # 160/40 deterministic seed 7
python -m pytest -q                      # 332 passed, 1 deselected
python -m evaluator.local_evaluator      # public-200: 0.880/0.4916/3.375/0.7400 results.json
python scripts/instrumented_eval.py --output evaluation/results/instrumented_results.json  # dev-160 control
# control verify (must be 160,144 before any comparison):
python -c "import json; d=json.load(open('runs/control-dev-newbaseline.json')); print(len(d['sessions']), sum(s['hit'] for s in d['sessions']))"
# per-session flips vs control:
python scripts/pool_miss_forensics.py --cases 160 --seed 7
```

## 4. Architecture (enough to rewrite)
- Simulator: hidden intent_card = 2 hard + 2 soft (180-char truncate, ~5% mid-word); turn1: buying discloses hard, browsing "still exploring"; loop respond→hit check→customer_reply(ask_attribute) → no preference if not on card; MTTC miss=11.
- Agent: neeshops/agent.py orchestrates S→I→H→B/V/F→R→N seam. ConversationState accumulates constraints (value-level staling 0.3, inferred decay 0.9, no wholesale erase), detects route (buying/browsing + _EXPLORATION_PHRASES override), 8-gate clarification (exhausted→turn9→confident margin0.15→wildcard×2→over-generality AND>200→agreement→entropy fallback, askable excludes brand/category), builds constraint_token_groups.
- Retrieval: TokenIndex (50k/95.5k terms, 3.5s, _LOOKUP_CACHE) exact AND + greedy backoff + price-gated fail-open + priority-union; BM25 FTS5 field-weighted + semantic hashed TF-IDF → hybrid RRF k=60 → guarantee pool front-loads exact AND, pads with corroborated/popular; filters demote-not-drop via token_index O(1).
- Ranking: ConstraintAwareRanker coverage = Σ w·idf·[group⊆doc] (stale 0.3), sort (violations, -coverage, -relevance minmax, -popularity, asin); rerank_limit 320 (full pool ~300, was 40); personalization soft weight 0.15 (selected 0.00 after weight sweep); LLMReranker gated (twins 10, margin 0.15, blend 0.15, limit 30, min_constraints 2, timeout 5s, flag false, model nvidia/nemotron-3-super-120b-a12b:free $0).
- Config: single neeshops/config/default_strategy.json, every key in research/experiment.py::SAFE_PARAMETERS (test_config_registered.py).
- Tests: pytest.ini, conftest fixtures; slowest test_multi_turn ~7s (re-parses catalog per Agent, no module fixture).

## 5. Round 1 — audit repairs + first hypothesis batch (2026-08-30..31)
Fork control: dev-80eee9a.json 141/160 (runs/dev-80eee9a.json). Baseline public 0.865/0.4470/3.52 (1652f46).

| Hypothesis | Code | Test | Result (dev-160) | Decision |
|---|---|---|---|---|
| Audit: false size/budget/wildcard | constraints.py context-gated size, budget keyword window8, slot==other skip, negation colour, brand scan | pytest + instrumented 200 | buying HR 0.8625→0.900, MRR +0.048 | shipped |
| Audit: truncation 40→320 | deterministic.py rerank_limit 320 | same | rescued 9 pool>40 but exposed 11 (net -2 on public) | shipped (tradeoff documented §5 P0) |
| Audit: still-exploring route | intent.py _EXPLORATION_PHRASES | browsing weights 0.7/0.3 vs 0.3/0.7 | semantic-heavy regressed browsing/boundary | kept 0.7/0.3 |
| Audit: one-turn lag | agent.py _preview_state | — | same-turn no-preference | shipped |
| Audit: override deactivate soft + cut query | state.py override_turn | — | HR 0.80→0.67 → reverted, kept override_turn log | reverted |
| Rank-salience buying-gated 0.2/1.0 | config buying_salience 0.2, popularity 1.0, deterministic route-aware weighting | runs/dev-94cafc0.json 144/160 +4/-1 vs 80eee9a (0112,0011,0085,0125 /0035) | 0.900/0.514/3.188 | merged 63757ad→new-baseline 46e3322; public 0.880 confirmed |
| Rank-coverage-idf padding sort + floor 60 | ranking/features + config rerank_floor_buying 60 | archive/dev-8a5e212, dev-5aac7bf | 0/0 flips, 141/160, 156/160 over-generality, 17 rank vs 2 pool ceiling 0.9875 | negative, decisive, not merged |
| Question-margin late-phase value | clarification margin_stop × other_max_asks grid hypothesis | archive/gate-report.question-margin.md 0/19 late-phase, 0/19 large collapse | dev already 3.319 vs 3.465 public | gate failed, no code |
| Boundary-override phrasebook + lag | constraints/intent/state phrasebook | archive/miss-reading.boundary-override.md 0 flips realistic, 1 forced (0112) | depths override 14-57 boundary 46-264, rank-dominated | negative |
| Route-attribution per-turn logging | research logging | no snapshot | diagnostic only | not merged |

## 6. Round 2 — second hypothesis batch (2026-08-31)
Control moved to new-baseline 46e3322 144/160 after rank-salience merged.

| Hypothesis | Code | Result (dev-160) | Decision |
|---|---|---|---|
| Global-salience 0.2 globally (not buying-gated) | config coverage_salience_weight 0.5→0.2 | archive/dev-e9cff6d 145/160 0.491/3.119 +1 vs new-baseline (0075,0092 /0112) | net +1 inside ±1 jitter → reverted 050f9df |
| Competition-window 80 + retrieval tie-break | deterministic window 80 + rank tie-break popularity→retrieval | archive/dev-9317100 145/160 0.492/3.119 same +2/-1 | +1 jitter → not merged |
| Uninformative-stop N=1 suppress wasted asks | clarification skip if no collapse | archive/dev-b9ef490 143/160 0.485/3.169 +1/-2 (67 wasted/160=0.419) | regressed, reverted 1a7c0d1 |
| Personalization weight 0.00 vs 0.03 | personalization weight sweep | evaluation/results/personalization_evaluation.json 0.89375 Hit both, MRR -0.00109, CI [-0.010,0.008] | selected 0.00 |
| Final audit forensics | sc-final-audit/runs/final-audit.md | 2 pool (depth 240-410, 823-1480) 13 rank 0/13 dropped | roadmap: pool expansion + deep features |

Noise floor: independent controls 159/160 → ±1 (~0.6pp) jitter; <3pp aggregate is noise. Paired flips are the signal.

## 7. Directory & branch cleanup (what was done for push)
- Archived branch-only artifacts into runs/archive/ (10 files, names preserve branch).
- Tagged each exp head as archive/exp-{name} (e.g. archive/exp-global-salience at e9cff6d) then git worktree remove sc-* and git branch -D exp/*, audit/final-forensics. Remaining branches: staging-main (current), master, origin/*.
- Removed stale runs/control-dev-forkpoint.json (contaminated 200-session copy, superseded by control-dev-newbaseline.json; backup preserved in archive).
- Deleted scripts/presentation/node_modules and added **/node_modules to .gitignore; removed outer nul, ShopCopilot/session_context.md duplicate, docs/presentation/SESSION_CONTEXT.md (plan dump, not needed for rebuild).
- All commits one logical change, pytest -q before each, snapshots cp evaluation/results/instrumented_results.json runs/dev-$(git rev-parse --short HEAD).json where applicable.

## 8. Slide deck rebuild (15 slides → SPEAKER_SCRIPT.md)
1 Title hero 0.880/0.4916/3.375/0.7400 + 50k + $0.00  2 Pipeline contract + funnel 50k→300→320→10 + 332 tests  3 Staircase starter→v2→shipped + TS decomposition 67% MRR  4 Innovation directions kept/killed table  5 Method 5 worktrees, pre-registered bars, paired flips, ±1 noise  6 Win salience 0.5→0.2 +4/-1 net+3  7 Transfer dev→public + per-scenario counts 74/80 etc  8 Graveyard 6 negatives + 0.906 not merged  9 Findings 4 (MTTC=first-hit, coupling 0104, dynamic route 89%, saturated permutations)  10 Miss map 2 pool /13 rank /0 dropped  11 Feasibility $0 0 tokens p50 330.1 p95 526.6  12 Business 9.8→3.4 turns  13 Readiness fresh-clone 0.880 + compliance  14 Roadmap pool sub-indices + deep features  15 Provenance tags + 3 reproduce commands.
Build: scripts/presentation/build_deck.js (pptxgenjs) → docs/presentation/*.pptx/.pdf; claim map docs/PRESENTATION.md.

## 9. Speaker script rebuild (~9 min)
File docs/SPEAKER_SCRIPT.md: cues [PAUSE][POINT][EMPHASIZE][REPEAT][SLOW][LOOK][ADVANCE], per-slide verbatim (S1 15s … S15 15s), Q&A 6 (deterministic vs LLM, 8-gate entropy, override staling, zero cost, anti-overfit dev-only tuning, boundary 6/10).
Tone: deliberate, data-grounded, no buzzwords; flips are hero.

## 10. Video script rebuild (2 min)
File docs/VIDEO_SCRIPT.md: storyboard with sampled-session language (never random), pre-take public_0112 / boundary / optional honest miss, freeze banner, M1-M3 S1-S8 demo features.

## 11. Report rebuild (REPORT.md)
Sections: abstract, scores, architecture diagram, retrieval, ranking, conversation, experiments (win + graveyard), forensics, feasibility, reproduce, attribution.

## 12. Push checklist
- Branch: staging-main ahead of origin/staging-main by N (commit HANDOVER + archive + cleanup). Do not push .env, data/, evaluation/results/bench_*.json, instrumented_results.json (gitignored).
- Remote: origin https://github.com/Shaneeen/ShopCopilot.git (or as configured); git push origin staging-main; tags: git push origin tag submission-freeze new-baseline fork-point archive/exp-*
- Verify: git diff --stat HEAD origin/staging-main empty after push; pytest -q 332 pass; python -m evaluator.local_evaluator 176/200.

---
Maintainer: update §5-6 after each new experiment, append docs/V3.md §10, and keep this as the single rebuild entry point.
