# Handover — Rebuild ShopCopilot From Scratch (2026-08-31, freeze 46e3322)

For the next human + AI. Everything needed to rewrite the scripts, rebuild the deck, and know what was tried in Round 1 vs Round 2 vs Round 3.

## 0. Where to start
1. `docs/HANDOVER.md` (this file) — canonical narrative: 3 rounds, master table, per-experiment detail, causal chain, graveyard (paste-ready for REPORT §2/3/5 and slides 6–10).
2. `docs/V3.md` — single technical handover (architecture, simulator, what shipped, levers, reproduce).
3. `docs/experiment-ledger.md` — metrics matrix + run inventory + ledger + gaps (tables, not prose).
4. `README.md` — frozen scores + quickstart.
5. `AGENTS.md` — experiment rules (dev-160 only, paired flips, SAFE_PARAMETERS, pytest 332).

## 1. What this is (30s)
TikTok TechJam 2026 Track 4. Headless agent, 10 turns max, top_k=10, 50k Clothing_Shoes_and_Jewelry catalog. 200 public sessions, 800 hidden (40/40/15/5 buying/browsing/override/boundary). Starter BM25: Hit 0.125, MRR 0.068, MTTC 9.81, Tech 0.1067. Tech=0.5*Hit+0.3*MRR+0.2*clip((11-MTTC)/10).
Thesis: maximize information per turn via exact uncertainty (TokenIndex AND size) → set-splitting questions, not better retrieval alone.
**Protocol:** every branch = one pre-registered hypothesis, forked into an isolated worktree from a tagged control, ship criteria written before the first eval, paired per-session flips vs control (not aggregates). Seed 7. Noise floor ±1 session (independent controls agree 159/160).

**Scoreboard: 7 experiments, 1 merged, 6 rejected — and every rejection redirected the next experiment.**

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
Parent sc-*/ worktrees removed after archiving; see §8.
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

## 5. Experiment History — 3 rounds + final audits (master table + detail)

### Master table

| # | Branch | Round | Hypothesis (one line) | Result | Effect | Disposition |
|---|---|---|---|---|---|---|
| 1 | `exp/rank-coverage-idf` | R1 | Buying misses are pool-composition (crowding in the 200-pool); fix padding to mirror ranker | Confirmed taxonomy (17 rank vs 2 pool) but **0/0 flips** — both pool levers never fire on dev | Pool-side levers are dead; lever is ranker-side | Rejected (decisive negative) |
| 2 | `exp/rank-salience` | R1 | Same misses come from feature **weights**: salience crowded out by popularity | **+4/−1** dev flips; Hit 0.900, MRR 0.514, MTTC 3.188 | Only merge of the project; confirmed on public-200; drives 67% of ΔTechScore | **MERGED** (`new-baseline` → `submission-freeze`) |
| 3 | `exp/question-margin` | R1 | Late-phase margin-gain question value can cut MTTC | **Gate failed: 0/19** — pattern absent; premise stale (3.465 MTTC was public-200; dev was already 3.319) | Saved an entire build; MTTC headroom on dev was ~0.12 turns, not 0.27 | Stopped at gate |
| 4 | `exp/boundary-override` | R1 | Override/boundary misses come from extraction lag & state-handling | Hypothesis **disproven by replay**: extraction same-turn, no re-asks, no lag; real pattern = rank-depth losses (override targets pool rank 14–57, boundary 46–264) + uninformative asks | Killed route-flip-fix before it was built; sized the R2 window (≥60); motivated uninformative-stop | Stopped (forensics only, no code shipped) |
| 5 | `exp/competition-window` | R2 | §5 P0 competition window + retrieval-rank tie-break frees top-10 slots | Gate passed (12/12 top-10 full-coverage; depths 12–147) but **+2/−1**, MRR −0.023, sweep-invariant (60/80/150 identical) | First of three identical results → ordering layer saturated | Rejected (failed ship criteria) |
| 6 | `exp/uninformative-stop` | R2 | Stop asking when disclosures exhaust → cuts MTTC | Gate passed (0.419 wasted/session) but MTTC **−0.019 only**; +1/−2 (0104 = bug). **Found: MTTC = first-hit turn; stopping can't move it** and **"hit-safe by construction" is FALSE** | Two structural facts; killed all stop-rule work; exposed message-stream→retrieval coupling | Reverted (hard fail: 2 hit→miss) |
| 7 | `exp/global-salience` | R2 | Salience reweight generalizes if ungated across routes | **+2/−1, same sessions as window**; MRR −0.023, boundary −1. Task 1: **route gate 89% vacuous** (84/94 non-buying sessions take buying turns; win set 4/4 leaked) | Explains R1's mystery; scenario labels ≠ runtime route; keep buying-gated 0.2/1.0 | Reverted (lever doesn't generalize; diagnostics landed on main) |
| 8 | `audit/final-forensics` | R3 | Pool misses fixable? Query dropping constraints? | Pool misses = **cap-depth** (target rank 201+), not filter bugs; query faithful, **0/13** dropped constraints | Closes the reordering era; roadmap = new information (recall layer, feature enrichment) | Audit only (e86ed01) |

### Per-experiment detail

#### 1. exp/rank-coverage-idf — "fix the pool"
- **Commits:** be95ae0 (miss taxonomy) · 8a5e212 (lexicographic padding sort) · 62e8403 (`rerank_floor_buying=60`) · f32294a (control restore)
- **Hypothesis:** target is in the pool but crowded out of top-10 among ~200 full-coverage AND members → make padding consistent with the ranker.
- **What it found:** taxonomy confirmed the miss class — **overall pool 2 / rank 17, rank_fix_ceiling 0.9875** (buying 1p/4r, browsing 0/5, override 0/6, boundary 1p/2r; detail: pool 2, rank 13, extraction 1, override_not_yet_delivered 3).
- **Why it failed anyway:** dev is over-generality-dominated (156/160; padded: 0 everywhere) → padding path never fires; floor-firing turns are already hits at pool rank 1–2 → widening can't flip. **Both levers provably inert on this split.**
- **Extra catch:** its own first MRR "gain" was one-session jitter (public_0142) — self-rejected before reporting.
- **Effect:** pool composition ruled out → ranker-side sort is the lever → directly motivated #2 (weights) and #5 (window). Plus it caught the **control corruption** (see cross-cutting events).

#### 2. exp/rank-salience — "fix the weights" ✅
- **Commits:** f251a14 (taxonomy) · 9791954 (route-aware weighting) · 94cafc0 (sweep) · snapshots f8b6a83
- **Hypothesis:** same miss class as #1, but mechanism = feature **weights**, not pool composition. Reweight the buying route: salience ↑, popularity ↓, config-driven.
- **Result:** sweep {0.2–0.4 / 0.8–1.0}, best **0.2/1.0** → dev-160 **Hit 0.900 / MRR 0.514 / MTTC 3.188** · flips **+4** (0031, 0085, 0100, 0125) **/−1** (0035).
- **Honest caveat:** failed its own buying-specific pre-registration (only 1 buying flip) — wins were route-general. Plateau at 0.900 across three parameter points (robust, not knife-edge).
- **Effect:** merged after the full ladder (dev → public-200 **0.880 / 0.4916 / 3.375 / 0.7400** vs 0.870 / 0.4455 / 3.465 / 0.7193). The MRR-dominant gain pattern matches the mechanism (+10.4% rel MRR = **67% of ΔTechScore**). Also seeded #7: *if the wins weren't buying-specific, does ungating help?*

#### 3. exp/question-margin — "smarter late-phase questions"
- **Commit:** c18fcf6 (gate report `runs/gate-report.md`)
- **Hypothesis:** late-phase set-entropy is exhausted; top-10 margin uncertainty isn't → margin-gain question value cuts MTTC (3.465 → 3.2).
- **Gate design:** profile every missed session's LAST question for "large set-collapse, flat margin-change" — build only if ≥1/3 of misses show it.
- **Result: 0/19. STOP.** Plus a premise correction discovered en route: 3.465 was the public-200 MTTC; true dev-160 MTTC was already 3.319 → headroom to 3.2 was only ~0.12 turns.
- **Effect:** zero build cost on a dead hypothesis; MTTC-as-target demoted a round early.

#### 4. exp/boundary-override — "fix the conversation"
- **Commits:** c0c8e2b (miss-reading + fresh control) · 6357840 (A/B evidence)
- **Hypothesis:** override (0.800) and boundary (0.800) slices lose turns to extraction/state lag — late boundary phrases, spurious re-asks.
- **Forensics (8 misses, full replay with materialized cards):** extraction is **already same-turn** (coverage 3/3, 2/2), the wildcard is never re-asked, overrides never re-asked → **§6.2.3 phrasebook was a no-op; refused to implement it.**
- **Actual patterns found:** (a) handshake flips route browsing→buying — but A/B by monkeypatch showed the route rule flips **0 sessions** (buying/browsing retrieval weights identical: bm25 0.7/sem 0.3) → cosmetic; (b) post-override target drops to **pool rank 14–57** (boundary: 46–264) while turns 4–6 burn on "I don't have an additional preference for F" until budget death at T6.
- **Effect:** killed the planned route-flip-fix branch before creation; delivered the depth data that sized #5's window (≥60) and motivated #6 (wasted asks). Third independent confirmation: **conversation-level levers cannot move ranks.**

#### 5. exp/competition-window — "shrink the competition"
- **Commits:** 9317100 (gate + window 80 + tie-break) · 0fa701a (snapshot)
- **Hypothesis:** §5 P0 window limiting full-coverage members competing for top-10 + retrieval-rank tie-break frees slots for the target.
- **Gate: PASSED** — fresh miss map at new-baseline: 15 = 2 pool + 13 rank; depths **12, 14, 17, 18, 28, 30, 36, 52, 64, 92, 122, 147**; 12/12 top-10s predominantly full-coverage (10/10).
- **Result:** window 80 → **Hit 0.90625 (145/160)** but MRR 0.4918 (−0.023), flips **+2/−1** (0075, 0092 / 0112); sweep 60/80/150 → **identical 2/1**. Ship criteria (≥3/≤1, MRR flat) failed on both counts.
- **Effect:** shallow band (12–18) is perturbation-rescuable; 0112 is knife-edge; **the window has no tuning room** — first evidence the ordering layer is saturated.

#### 6. exp/uninformative-stop — "stop wasting turns"
- **Commits:** 009f5b7 (gate instrumentation) · b9ef490 (N=1 stop rule) · 1a7c0d1 (revert)
- **Hypothesis:** post-override asks all return "no additional preference" → stopping early cuts MTTC (gate: 0.419 wasted turns/session — passed; boundary 2.857).
- **Result: MTTC −0.019 only** (< 0.10 bar); flips +1/−2 with 0104 flagged as **bug, not tuning** → reverted under the zero-hit→miss rule.
- **Two structural discoveries (the real yield):**
  1. **MTTC = first-hit turn** (miss = 11) → wasted asks occur *after* the hit or in doomed sessions → no stop rule can ever move MTTC. The lever is "hit sooner."
  2. **"Hit-safe by construction" is FALSE** — stopping changes `user_messages` → retrieval → recommendations (0104 is the proof). Conversation and retrieval are coupled through the message stream.
- **Effect:** killed all stop-rule/conversation work permanently; finding #2 motivated the query-faithfulness audit (#8).

#### 7. exp/global-salience — "does it generalize?"
- **Commits:** 9d6f544 (route-per-turn logging) · e9cff6d (ungate 0.2) · 050f9df (revert)
- **Task 1 (route attribution — the longest-shelf-life result of round 2):** **84/94 (89%) of non-buying sessions spend ≥1 turn on the buying route** (browsing 57/65, boundary 5/7, override 22/22); all 15 misses are majority-buying-route; the R1 win set leaked 4/4 (e.g. 0112 = [browsing, buying×9]).
- **Result:** ungated 0.2 → +2/−1, **same sessions as the window** (0075, 0092 / 0112), MRR −0.023, boundary 0.571→0.428; 0.35 variant identical. Failed ship → reverted to per-route 0.5/0.2 (the merged baseline).
- **Effect:** (a) explains why R1's buying-gated change won on non-buying sessions; (b) with #5, completes the **three-way convergence** — reweight, window, and stop-rule all produce the identical +2/−1 → the ordering layer is saturated and the remaining misses need *new information*; (c) route-gate weakness documented for the roadmap.

#### 8. audit/final-forensics (read-only) — "why do we still miss?"
- **Commit:** e86ed01 (`runs/final-audit.md`)
- **Pool misses (2):** cap-depth — target ranks 201+ under current pool construction; **no filter bug**. Fixable only by a recall layer.
- **Query faithfulness (13 deep misses):** per-turn diff of extracted constraints vs actual retrieval query → **0/13 dropped or relaxed**. The query is faithful; depth 28–147 misses are genuine capability limits of the current feature space.
- **Effect:** closes the investigation era with two quantified ceilings; defines round 4 (new information, not reordering).

### Cross-cutting events (not branch-specific)

| Event | What happened | Effect |
|---|---|---|
| **Control corruption** | Committed `control-dev-forkpoint.json` was a public-200 artifact (200 sessions, Hit 0.855); caught independently by two agents (#1, #4) | True dev-160 control regenerated (160 sessions, 144 hits, 0.88125/0.4430/3.319); AGENTS.md rule 10 added: verify control before any comparison |
| **Noise floor calibration** | Independent control reproductions agree 159/160; public_0142 MRR jitter isolated | ±1 session = jitter; single-session MRR moves never reported as wins |
| **Test count drift** | 248 (docs) vs 325 actual (fork point includes audit repairs) | Docs fixed; every later prompt states 325 |
| **Diagnostic cherry-picks** | 9d6f544 (route logging) + 009f5b7 (wasted-ask instrumentation) landed on main after R2 | Future evals carry the instrumentation for free |

### The causal chain (how each result chose the next experiment)

```
R1 #1 coverage-idf ──(pool levers dead)──┐
R1 #2 salience ──(won, but not buying-   │──► R2 #5 window (ranker-side)
    specific; wins leaked routes) ───────┤──► R2 #7 ungate A/B
R1 #4 boundary ──(depth 14–57/46–264;    │──► R2 window sized ≥60
    wasted asks found) ──────────────────┘──► R2 #6 uninformative-stop
R1 #3 question-margin ──(MTTC headroom stale)──► MTTC demoted as target

R2 #5 + #6 + #7 ──(identical +2/−1; MRR −0.023)──► ORDERING SATURATED
R2 #6 ──(message→retrieval coupling)─────────────► R3 audit: query faithful (0/13)
R3 audit ──(cap-depth 201+; features are the limit)──► ROADMAP: recall layer,
                                                        feature enrichment, hit-sooner
```

**Levers exhausted vs. open:**

| Lever | Status | Evidence |
|---|---|---|
| Pool composition (padding, floor) | ❌ dead | #1: 0 flips, path never fires |
| Feature weights (buying-gated) | ✅ shipped | #2: merged, confirmed |
| Ordering (window, tie-break, ungate) | ❌ saturated | #5, #7: identical 2/1, MRR cost |
| Conversation (stop rules, question value) | ❌ structurally inert | #3 gate, #6 bug + MTTC finding |
| Query faithfulness | ✅ verified clean | #8: 0/13 drops |
| **New information (recall, features)** | 🔓 open | #8: cap-depth + depth 28–147 |

### One-line graveyard (deck slide 8)

> **rank-salience +3 ✅ merged · competition-window +1 · global-salience +1 · uninformative-stop −1 · rank-coverage-idf 0 · question-margin gate-stopped · boundary-override disproven** — *every red bar was rejected by criteria written before the experiment ran.*

Two notes on use: (1) the flip session ids here are dev-160 ids at each branch's own control — don't sum them across branches (0075/0092 appear in three reports; that's one session three mechanisms competed over, not three wins); (2) ledger `docs/experiment-ledger.md` §3 is the provenance shas, this is the hypothesis→effect narrative — keep both and cross-link.

## 6. Round 2–3 quick reference (for deck/report copy-paste)

Convergence: #5+6+7 identical +2/-1 → ordering layer saturated; roadmap is new information. Personalization weight 0.00 selected (0.89375 both, MRR −0.00109 CI [-0.010,0.008]). Noise floor: 159/160 → ±1 jitter; <3pp aggregate is noise. Paired flips are signal.

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
Maintainer: update §5 after each new experiment, append docs/V3.md §10, and keep this as the single rebuild entry point.
