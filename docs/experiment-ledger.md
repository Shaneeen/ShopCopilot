# 1 METRICS MATRIX

`MISSING` means the swept artifacts do not record the value. Splits are identified by observed session count, not inferred from filenames. The simulator seed expected by the runbook is **7** (`docs/V3.md` §7), but the instrumented run JSONs contain no seed field; their seed is therefore **MISSING**. The standalone benchmark does record seed **7** (`evaluation/results/bench_v1.json:meta.seed`).

| Experiment / artifact | Split (sessions) | Seed | Hit@10 | MRR | MTTC | TechnicalScore | p50 / p95 ms | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| v2 `6f7dd75` | public (200) | MISSING | 0.870 | 0.4455 | 3.465 | 0.7193 | ~230 / MISSING | shipped; `docs/V3.md` §10 |
| same-env baseline `1652f46` | public (200) | MISSING | 0.865 | 0.4470 | 3.52 | 0.7162 | MISSING | comparison baseline; `docs/V3.md` §1/§10 |
| audit repairs `8d8822e` | public (200) | MISSING | 0.855 (171/200) | 0.438240 | 3.590 | 0.707172 | 357.0 / 564.7 | shipped on `origin/master`; `exp/boundary-override:runs/control-dev-forkpoint.public200.bak.json` |
| fork-point `80eee9a` | dev (160) | MISSING | 0.88125 (141/160) | 0.438810 | 3.31875 | 0.725893 | 565.4 / 1001.2 | control; `runs/dev-80eee9a.json` |
| taxonomy instrumentation `f251a14` | dev (160) | MISSING | 0.88125 (141/160) | 0.442976 | 3.31875 | 0.727143 | 440.8 / 856.4 | diagnostic; `runs/dev-f251a14.json` |
| buying-gated salience baseline `9791954` | dev (160) | MISSING | 0.88125 (141/160) | 0.438810 | 3.31875 | 0.725893 | 316.8 / 526.1 | neutral; `runs/dev-9791954.json` |
| rank-salience best `94cafc0` | dev (160) | MISSING | 0.90000 (144/160) | 0.514395 | 3.18750 | 0.760568 | 432.4 / 783.3 | merged; `runs/dev-94cafc0.json` |
| new-baseline control `46e3322` | dev (160) | MISSING | 0.90000 (144/160) | 0.514395 | 3.18750 | 0.760568 | 330.1 / 526.6 | authoritative control; `runs/control-dev-newbaseline.json` |
| new-baseline `46e3322` / `submission-freeze` | public (200) | MISSING | 0.88000 (176/200) | 0.491585 | 3.37500 | 0.739976 | MISSING | measured confirmation; `results.json`, annotated tag `submission-freeze` |
| padding sort `8a5e212` | dev (160) | MISSING | 0.88125 (141/160) | 0.438810 | 3.31875 | 0.725893 | 541.7 / 937.0 | negative; `exp/rank-coverage-idf:runs/dev-8a5e212.json` |
| padding snapshot `5aac7bf` | dev (160) | MISSING | 0.88125 (141/160) | 0.438810 | 3.31875 | 0.725893 | 319.0 / 524.1 | negative; `exp/rank-coverage-idf:runs/dev-5aac7bf.json` |
| global salience `e9cff6d` | dev (160) | MISSING | 0.90625 (145/160) | 0.490992 | 3.11875 | 0.758048 | 575.0 / 1021.0 | reverted; `exp/global-salience:runs/dev-e9cff6d.json` |
| competition window 80 + tie-break `9317100` | dev (160) | MISSING | 0.90625 (145/160) | 0.491763 | 3.11875 | 0.758279 | 394.2 / 702.6 | branch-only; `exp/competition-window:runs/dev-9317100.json` |
| uninformative-stop N=1 `b9ef490` | dev (160) | MISSING | 0.89375 (143/160) | 0.484663 | 3.16875 | 0.748899 | 482.6 / 855.8 | regressed/reverted; `exp/uninformative-stop:runs/dev-b9ef490.json` |
| personalization weight 0.00 | dev (160) | MISSING | 0.89375 | 0.490104 | 3.225 | MISSING | MISSING | selected; `evaluation/results/personalization_evaluation.json:weight_sweep[0]` |
| personalization weight 0.03 | dev (160) | MISSING | 0.89375 | 0.489010 | 3.225 | MISSING | MISSING | negative; `evaluation/results/personalization_evaluation.json:weight_sweep[1]` |
| fake-LLM anchor | bench (4) | 7 | 1.000 | 0.392 | MISSING | MISSING | 301.1 / MISSING | diagnostic only; `evaluation/results/bench_v1.json` |
| holdout confirmation | holdout (40) | 7 expected | MISSING | MISSING | MISSING | MISSING | MISSING | no result artifact found; split size/runbook in `docs/V3.md` §2/§7 |

Scenario split for the authoritative dev control is buying **66**, browsing **65**, intent_override **22**, boundary **7** (`runs/control-dev-newbaseline.json:panel.scenario_metrics`). Their Hit@10 values are respectively **0.924242**, **0.953846**, **0.772727**, **0.571429**; MRR **0.557209**, **0.486752**, **0.534704**, **0.303571**; MTTC **2.530303**, **2.707692**, **5.5**, **6.571429** (`runs/control-dev-newbaseline.json:panel.scenario_metrics`).

# 2 RUN INVENTORY

| Artifact (working tree or historical ref) | Identity / contents | Provenance caveat |
|---|---|---|
| `runs/control-dev-newbaseline.json` | 160 sessions, 144 hits; panel in matrix | authoritative paired control at `46e3322`; seed MISSING |
| `runs/dev-80eee9a.json` | 160 sessions, 141 hits | fork-point snapshot |
| `runs/dev-f251a14.json` | 160 sessions, 141 hits | taxonomy instrumentation snapshot |
| `runs/dev-9791954.json` | 160 sessions, 141 hits | route-aware weighting baseline |
| `runs/dev-94cafc0.json` | 160 sessions, 144 hits | merged rank-salience best |
| `exp/rank-coverage-idf:runs/dev-8a5e212.json` | 160 sessions, 141 hits | branch-only historical artifact |
| `exp/rank-coverage-idf:runs/dev-5aac7bf.json` | 160 sessions, 141 hits | branch-only historical artifact |
| `exp/competition-window:runs/dev-9317100.json` | 160 sessions, 145 hits | branch-only historical artifact |
| `exp/global-salience:runs/dev-e9cff6d.json` | 160 sessions, 145 hits | branch-only historical artifact |
| `exp/uninformative-stop:runs/dev-b9ef490.json` | 160 sessions, 143 hits | branch-only historical artifact |
| `exp/boundary-override:runs/control-dev-forkpoint.json` | 160 sessions, 141 hits | corrected control; MRR 0.442976 (`runs/miss-reading.md` on that ref) |
| `exp/boundary-override:runs/control-dev-forkpoint.public200.bak.json` | 200 sessions, 171 hits | mislabeled old public artifact preserved on branch |
| `exp/question-margin:runs/gate-report.md` | 160-session gate report, 19 misses | no variant run JSON |
| `exp/uninformative-stop:runs/gate-report.md` | 160-session gate report | measurement run says 145/160 and is not preserved as a named JSON on the ref |
| `exp/boundary-override:runs/miss-reading.md` | replay of 29 override+boundary sessions and 8 reported misses | report text says “all 8” while its categorization lists 9 IDs; see GAPS |
| `results.json` | 200 sessions, 176 hits; Hit 0.88000, MRR 0.491585, MTTC 3.37500, Tech 0.739976 | public confirmation produced at `46e3322`; frozen by annotated tag `submission-freeze`; seed MISSING |
| `evaluation/results/instrumented_results.json` | 160 sessions, 144 hits | untracked/ignored mutable output; numerically matches new-baseline control |
| `evaluation/results/bench_v1.json` | 4 cases, seed 7, workers 1, fake-LLM arm | only committed benchmark JSON found across refs |
| `evaluation/results/personalization_evaluation.json` | 160-session weight sweep | seed MISSING |
| `runs/control-dev-forkpoint.json` | untracked working-tree file | pre-existing and untouched; 160-session content, but not authoritative under `AGENTS.md` |

No `runs/*.md` exists in the current working tree; the three Markdown reports above exist only on experiment refs. No other `evaluation/results/*.json` was found across refs. Counts and identities come directly from the cited JSONs and `git ls-tree -r` over all local heads, remotes, and tags.

# 3 EXPERIMENT LEDGER

- **audit repairs (`8d8822e`)** — public-200 fell from same-env baseline **0.865/0.4470/3.52/0.7162** to **0.855/0.4382/3.59/0.7072** (Hit/MRR/MTTC/Tech), with **9 miss→hit** and **11 hit→miss** reported but IDs MISSING (`docs/V3.md` §1, §5, §10). Shipped on `origin/master`; not merged into current `staging-main` history.
- **rank-salience (`9791954`, `94cafc0`, snapshot `f8b6a83`)** — buying-gated salience **0.2** / popularity **1.0** reached **144/160**, +4/−1 vs `dev-80eee9a`; miss→hit `public_0112`, `public_0011`, `public_0085`, `public_0125`; hit→miss `public_0035` (`runs/dev-80eee9a.json`, `runs/dev-94cafc0.json`). Merged at `63757ad`; new-baseline public-200 confirmation is **0.88000/0.491585/3.37500/0.739976** at `46e3322` (`results.json`, annotated tag `submission-freeze`); holdout confirmation MISSING.
- **rank-coverage-idf (`8a5e212`, `5aac7bf`, `62e8403`)** — lexicographic padding sort and buying rerank floor **60** produced **0/0** flips and remained **141/160**; dev had **156/160** over-generality sessions, miss taxonomy **17 rank / 2 pool**, rank-fix ceiling **0.9875** (`exp/rank-coverage-idf:runs/dev-8a5e212.json`, `.../dev-5aac7bf.json`, `docs/V3.md` §10). Negative, unmerged.
- **question-margin (`c18fcf6`)** — among **19** misses, last question existed and was measurable in **19/19**, large collapse ≥30% was **0/19**, late-phase measurable was **0/19**, and the hypothesized pattern was **0/19** (`exp/question-margin:runs/gate-report.md`). Gate failed; no code variant or flips.
- **boundary-override (`6357840`)** — **29** relevant sessions (override **22**, boundary **7**) were replayed; reported override target depth **14–57**, boundary **46–264**; realistic boundary route monkeypatch gave **0** flips and **0** regressions, while forced-browsing ceiling flipped only `public_0112` miss→hit (`exp/boundary-override:runs/miss-reading.md`). Negative; no code change merged.
- **route-attribution (`9d6f544`, branch at `46e3322`)** — added per-turn route logging; no standalone result snapshot or flips found (`git log --all`, `refs/heads/exp/route-attribution`). Unmerged.
- **global-salience (`e9cff6d`, snapshot `05e3cd9`, revert `050f9df`)** — **145/160**, MRR **0.490992**, MTTC **3.11875**; miss→hit `public_0075`, `public_0092`; hit→miss `public_0112` vs new control (`exp/global-salience:runs/dev-e9cff6d.json`, `runs/control-dev-newbaseline.json`). Net +1 is inside the documented ±1-session jitter; reverted.
- **uninformative-stop (`009f5b7`, `b9ef490`, snapshot `7bf2bdf`, revert `1a7c0d1`)** — gate measured **67** wasted asks / **160** = **0.4188** turns/session and **23/160** sessions affected (`exp/uninformative-stop:runs/gate-report.md`). N=1 produced **143/160**, MRR **0.484663**, MTTC **3.16875**, with miss→hit `public_0075`; hit→miss `public_0112`, `public_0104` (`exp/uninformative-stop:runs/dev-b9ef490.json`). Reverted.
- **competition-window (`9317100`, snapshot `0fa701a`)** — window **80** plus retrieval tie-break reached **145/160**, MRR **0.491763**, MTTC **3.11875**; miss→hit `public_0075`, `public_0092`; hit→miss `public_0112` (`exp/competition-window:runs/dev-9317100.json`). Branch-only, unmerged; net +1 is inside jitter.
- **personalization (`3044e5e`, `e1eeb5a`)** — weight **0.03** held Hit at **0.89375** but changed MRR **0.490104→0.489010** (Δ **−0.001094**), with **2** improved, **5** worsened, **153** unchanged and bootstrap 95% CI **[−0.010231, 0.008229]**; selected weight **0.00** (`evaluation/results/personalization_evaluation.json`). Not present as a distinct merge into current `staging-main` after the historical combined-branch merges.
- **speed-refactor (`cfcd734`)** — singleton catalog, thread-local FTS, ProcessPool for CPU arms, `--diag`, module fixture; merged to `master` at `80eee9a`, then incorporated into current line through rank-salience merge `63757ad` (`git show cfcd734`, `git show 63757ad`). No dedicated before/after benchmark artifact found.
- **LLM benchmark** — four-case fake arm had **4/4** hits, MRR **0.392**, p50 **301.1 ms**, **9** calls, **3,780** prompt and **162** completion tokens, estimated **$0.000665**, wall **24.0 s** (`evaluation/results/bench_v1.json`). Live GPT-4o-mini is documented separately under LLM/COST/LATENCY; Nemotron confirmation MISSING.

# 4 MERGED-CHANGE TIMELINE

- `6f7dd75` (2026-08-30): v2 shipped, public-200 **0.870** Hit, **0.4455** MRR, **3.465** MTTC, **0.7193** Tech (`docs/V3.md` §10).
- `1652f46` (2026-08-30): merged `origin/clar` reliability harness while retaining v2 guarantee pool (`git log --all`); same-env public baseline **0.865/0.4470/3.52/0.7162** (`docs/V3.md` §1).
- `8d8822e` (2026-08-30): audit repairs committed on `origin/master`; public-200 **171/200** (`exp/boundary-override:runs/control-dev-forkpoint.public200.bak.json`). This commit is not an ancestor of current `staging-main`.
- `cfcd734` then merge `80eee9a` (2026-08-30): speed refactor landed on `master`; dev snapshot **141/160** (`runs/dev-80eee9a.json`).
- `e05b379` (2026-08-30): miss taxonomy instrumentation added (`git log --all`); no dedicated e05b379 run file, but `runs/dev-f251a14.json` records the related taxonomy panel.
- `63757ad` (2026-08-31): merged `exp/rank-salience`, including snapshots `9791954`, `94cafc0`, `f251a14`; best **144/160** (`git show 63757ad`, `runs/dev-94cafc0.json`).
- `f65f9f5` (2026-08-31): created `AGENTS.md` with the new-control/noise rules; this is the sole `AGENTS.md` history entry (`git log -p --all -- AGENTS.md`).
- `46e3322` (2026-08-31): committed authoritative new-baseline control **144/160**, tagged `new-baseline` (`runs/control-dev-newbaseline.json`, `git log --all`).
- `submission-freeze` at `46e3322` (2026-08-31): public-200 measured **176/200**, MRR **0.491585**, MTTC **3.37500**, TechnicalScore **0.739976** (`results.json`, annotated tag `submission-freeze`).

Current `staging-main` is `46e3322`. No global-salience, uninformative-stop, competition-window, question-margin, boundary-override, route-attribution, or rank-coverage-idf implementation is merged there; their refs remain separate (`git for-each-ref`).

# 5 CHART DIAGNOSTICS

- **Do not put public-200, dev-160, and bench-4 on one performance trend.** Their session counts differ (**200**, **160**, **4**) and the bench is hand-authored anchors (`docs/V3.md` §10; `evaluation/results/bench_v1.json`).
- **The old `control-dev-forkpoint.json` was contaminated by a public-200 artifact.** The preserved backup has **200** sessions while the corrected file has **160** (`exp/boundary-override:runs/control-dev-forkpoint.public200.bak.json`, `...:runs/control-dev-forkpoint.json`). Any chart sourced by filename alone is invalid.
- **Latency is not comparable across snapshots without environment/run controls.** Identical scoring panels appear with p50 **565.4**, **316.8**, **432.4**, and **330.1 ms** in `runs/dev-80eee9a.json`, `runs/dev-9791954.json`, `runs/dev-94cafc0.json`, and `runs/control-dev-newbaseline.json`. Plot latency as run-specific observations, not causal deltas.
- **Old taxonomy schema has a chart-breaking unit change.** `runs/dev-f251a14.json:panel.rank_fix_ceiling` is count **17**, while `runs/control-dev-newbaseline.json:panel.rank_fix_ceiling` is rate **0.9875** after merge conflict resolution at `63757ad`. Never combine these in one numeric series.
- **Negative `filter_kill_rate` values are derived diagnostic artifacts, not literal rates.** New control is **−0.0202** overall and boundary **−0.186** (`runs/control-dev-newbaseline.json`); label the calculation explicitly rather than charting as physical “kills.”
- **Noise floor dominates most branch wins.** Independent controls agree on **159/160**, i.e. ±**1** session (~**0.6 pp**), and aggregate Hit differences below ~**3 pp** are designated noise (`AGENTS.md` lines 16–18). Global salience and competition-window are each net +**1** session; neither is confirmed.
- **Scenario percentages have small denominators.** Boundary dev has **7** sessions, so one flip is **1/7**; public boundary has **10** (`runs/control-dev-newbaseline.json`, `exp/boundary-override:runs/control-dev-forkpoint.public200.bak.json`). Show counts beside rates.
- **Rank-salience improves Hit and MRR together, but the baseline changed.** Its +4/−1 comparison is against `dev-80eee9a`, while later branch experiments compare against `control-dev-newbaseline`; charts must mark the control fork (`runs/dev-80eee9a.json`, `runs/control-dev-newbaseline.json`).

# 6 LLM/COST/LATENCY

- LLM reranking is off by default (`docs/V3.md` §4.1). Proposed Nemotron model is `nvidia/nemotron-3-super-120b-a12b:free`, priced **$0** with RPD **1000**; gates are twins **10**, margin **0.15**, blend epsilon **0.15**, rerank limit **30**, minimum constraints **2**, timeout **5 s** (`docs/V3.md` §6.3).
- Ship criteria are ΔHit ≥ **+0.03**, ΔMRR ≥ **+0.02**, trigger ≤ **30%**, added p95 ≤ **2 s** (`docs/V3.md` §6.3). No 20- or 100-case live Nemotron result exists: **MISSING** (`docs/V3.md` §10).
- Documented four-anchor no-LLM: Hit **1.0**, MRR **0.392**, p50 **299 ms**, wall **24.0 s**; live GPT-4o-mini: Hit **1.0**, MRR **0.392**, p50 **756 ms**, wall **33.7 s**, reported added latency **454 ms**; fake-LLM: Hit **1.0**, MRR **0.392**, p50 **301 ms**, wall **24.0 s** (`docs/V3.md` §10). Live token count and dollar cost are **MISSING**.
- Committed fake-LLM JSON records average **314.9 ms**, p50 **301.1 ms**, **9** calls, **3,780** prompt tokens, **162** completion tokens, estimated **$0.000665**, wall **24.0 s**, model `fake`, seed **7**, workers **1** (`evaluation/results/bench_v1.json`). Because the model is fake, that dollar amount is an estimator output, not a billed cost.
- Twelve-case no-LLM diagnostic: Hit **0.75**, MRR **0.37**, p50 **310 ms**, wall **75.8 s**, composition **2 easy / 2 medium / 3 hard / 5 insane**, insane Hit **0.6** (`docs/V3.md` §10). The corresponding JSON is MISSING.
- Public evaluation cost is documented as **~1,100** turns for **200** sessions, **~0.35–0.9 s** per `respond()`, and **~5–7 min** wall; a four-variant ablation is **~1,400** turns (`docs/V3.md` §1). These are source-reported approximate values and are not promoted to exact measurements.
- Dev new-control latency is p50 **330.1 ms**, p95 **526.6 ms**, with **0** LLM fallback turns (`runs/control-dev-newbaseline.json`). Audit public is p50 **357.0 ms**, p95 **564.7 ms**, also **0** fallback turns (`exp/boundary-override:runs/control-dev-forkpoint.public200.bak.json`).

# 7 GAPS

- Seed is absent from every instrumented run JSON: **MISSING**. Seed **7** is explicit only in `evaluation/results/bench_v1.json` and the reproduction command in `docs/V3.md` §7.
- Holdout-40 confirmation for merged rank-salience/new-baseline is **MISSING**. Public-200 is now measured at **0.88000/0.491585/3.37500/0.739976** (`results.json`, annotated tag `submission-freeze`).
- Full public audit paired IDs for the reported **9 miss→hit / 11 hit→miss** are **MISSING**; only examples `public_0085`, `public_0125`, `public_0090` are named (`docs/V3.md` §5).
- No result JSON exists for question-margin, boundary-override monkeypatches, route-attribution, the uninformative-stop measurement gate, the 12-case no-LLM bench, or live GPT-4o-mini; only Markdown summaries/commit messages survive (`runs/gate-report.md` and `runs/miss-reading.md` on experiment refs; `docs/V3.md` §10).
- `exp/boundary-override:runs/miss-reading.md` says “all **8** misses” but names **6** override IDs plus **3** boundary IDs (**9** unique IDs). The report also says “none of the **8**”; the true denominator is unresolved and must remain **MISSING** rather than corrected by inference.
- The uninformative-stop gate report says measurement panel **145/160**, but its JSON was not preserved; `dev-b9ef490.json` is the later N=1 variant at **143/160** (`exp/uninformative-stop:runs/gate-report.md`, `...:runs/dev-b9ef490.json`).
- `runs/dev-f251a14.json` stores `rank_fix_ceiling` as count **17**, unlike later rate-valued panels; schema/version metadata is **MISSING**.
- Exact commands, machine identity, environment hash, catalog hash, and timestamps are absent from most run JSONs: **MISSING**. This blocks strict latency reproducibility.
- No dedicated speed-refactor before/after benchmark was found, so its performance gain is **MISSING** despite the merged implementation (`cfcd734`).
- No tags beyond `fork-point` and `new-baseline` and no experiment refs beyond those inventoried were found (`git for-each-ref`). `AGENTS.md` has exactly one historical patch, commit `f65f9f5` (`git log -p --all -- AGENTS.md`).
