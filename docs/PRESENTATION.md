# ShopCopilot — Presentation Claim-to-Evidence Map

Every quantitative claim, table entry, and structural finding presented in `ShopCopilot_TechJam_Deck.pptx`, `ShopCopilot_TechJam_Deck.pdf`, `SPEAKER_SCRIPT.md`, and `REPORT.md` is mapped directly to authoritative artifacts in the repository.

---

## Slide-by-Slide Claim Map

| Slide | Claim / Metric / Statement | Authoritative Source Artifact | Exact Location / Citation |
|---|---|---|---|
| **S1: Title** | Hit@10: 0.880, MRR: 0.4916, MTTC: 3.375, TS: 0.7400 | `results.json` | `hit_rate_at_10`, `mrr`, `mttc`, `recommended_technical_score` |
| **S1: Title** | 50,000 catalog items | `data/catalog.jsonl` | Line count = 50,000 products |
| **S1: Title** | 0 tokens / $0.00 model cost | `results.json` | `reported_token_usage: {total_tokens: 0}` |
| **S2: System** | Starter baseline: Hit 0.125, MRR 0.068, MTTC 9.81 | `docs/baseline_results.json` / `docs/V3.md` | `docs/V3.md` §10 table row 1 |
| **S2: System** | Funnel: 50k → ~300 candidates → 320 cap → top 10 | `neeshops/config/default_strategy.json` | `candidate_limit: 300`, `deterministic.rerank_limit: 320` |
| **S2: System** | 332 automated tests | `tests/` | `python -m pytest -q` (332 passed, 1 deselected) |
| **S3: Staircase** | v2 pre-exp baseline: Hit 0.870, MRR 0.4455, MTTC 3.465, TS 0.7193 | `docs/V3.md` | `docs/V3.md` §10 row 1 |
| **S3: Staircase** | Official TechnicalScore formula | `evaluator/local_evaluator.py` | Line 312 (`0.5*hit + 0.3*mrr + 0.2*efficiency`) |
| **S3: Staircase** | Gain decomposition: 67% MRR, 24% Hit, 9% Efficiency | Calculated from `results.json` vs `docs/V3.md` §10 | ΔTS = +0.0207; MRR Δ = +0.0138 (66.7%), Hit Δ = +0.0050 (24.2%), Eff Δ = +0.0018 (8.7%) |
| **S4: Innovation** | Question margin gate: 0/19 triggered | `docs/experiment-ledger.md` §3 / `exp/question-margin` | `exp/question-margin:runs/gate-report.md` |
| **S4: Innovation** | Personalization: weight 0.03 worsened MRR | `docs/experiment-ledger.md` §3 | `evaluation/results/personalization_evaluation.json` |
| **S4: Innovation** | LLM live probe: Δ=0, +454 ms latency | `docs/V3.md` §10 | `docs/V3.md` §10 row 3 (`bench 4 anchor openrouter gpt-4o-mini`) |
| **S5: Method** | 5 isolated experiment worktrees | Git history / worktree refs | `sc-rank-salience`, `sc-rank-coverage-idf`, etc. |
| **S5: Method** | Measured noise floor: ±1 session (159/160 match) | `docs/experiment-ledger.md` §5 | Section 5 (identical control replays) |
| **S6: The Win** | +4 / −1 paired flips (+3 net, 141 → 144) | `runs/dev-94cafc0.json` vs `runs/dev-80eee9a.json` | Flips: `public_0031`, `0100`, `0085`, `0125` vs `0035` |
| **S6: The Win** | Salience reweight: 0.5 → 0.2 | `neeshops/config/default_strategy.json` | `coverage_salience_weight: 0.5`, `buying_salience_weight: 0.2` |
| **S7: Progression** | Dev-160: 0.900 Hit, 0.5144 MRR, 3.188 MTTC | `runs/control-dev-newbaseline.json` | `panel: {hit_rate_at_10: 0.9, mrr: 0.514395, mttc: 3.1875}` |
| **S7: Progression** | Per-scenario counts: 74/80, 73/80, 23/30, 6/10 | `results.json` | `scenario_metrics` sub-objects |
| **S8: Graveyard** | 6 non-shipped experiments & logs | `docs/experiment-ledger.md` §1 & §3 | Matrix rows: global-salience, competition-window, uninformative-stop, rank-coverage-idf, question-margin, boundary-override |
| **S8: Graveyard** | 0.90625 unmerged hit rate | `docs/experiment-ledger.md` §1 | `exp/global-salience:runs/dev-e9cff6d.json` |
| **S9: Findings** | MTTC = first hit turn | `evaluator/local_evaluator.py` | Line 301 (`if target in recommendations: break`) |
| **S9: Findings** | Conversation ↔ retrieval coupling (session 0104) | `exp/uninformative-stop:runs/dev-b9ef490.json` | Paired diff vs control |
| **S9: Findings** | Dynamic scenario switching (89% browsing → buying) | `neeshops/conversation/intent.py` | Route transition when constraints > 0 |
| **S9: Findings** | Saturated ranking permutations (+2/−1 identical) | `docs/experiment-ledger.md` §3 | `exp/global-salience` and `exp/competition-window` |
| **S10: Miss Map** | 2 pool misses (depth 240–410, 823–1480) | `runs/control-dev-newbaseline.json` | `panel.miss_decomposition: {pool: 2, rank: 10, ...}` |
| **S10: Miss Map** | 0/13 dropped constraints | `sc-final-audit/runs/final-audit.md` | Forensic extraction trace |
| **S11: Feasibility** | Latency: p50 330.1 ms, p95 526.6 ms | `runs/control-dev-newbaseline.json` | `panel.p50_latency_ms`, `panel.p95_latency_ms` |
| **S11: Feasibility** | Hardware & OS disclosure | `docs/final-eval-record.md` | CIM capture |
| **S13: Readiness** | Fresh-clone rehearsal score (0.880) | `docs/final-eval-record.md` | Clean reproduction stdout |
| **S15: Provenance** | Tag chain: `fork-point`, `new-baseline`, `submission-freeze` | Git tags at `46e3322` | `git tag --list` |
| **S15: Provenance** | Dataset attribution | `DATA_ATTRIBUTION.md` | Julian McAuley Amazon Reviews 2023 |
