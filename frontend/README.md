# ShopCopilot — Finding the Hidden Product

> **TikTok TechJam 2026 · Track 4 · Team Anything Ah**
>
> **The task:** a customer with a hidden target product inside a 50,000-item
> catalog. Our job: surface it in the Top-10 within 10 conversational turns.
> **We do it 88% of the time in ~3.4 turns — with zero external LLM calls.**

---

## Headline results

*Official evaluator (`evaluator/local_evaluator.py`), 200 public sessions,
50,000 catalog items, submission freeze `46e3322` (`results.json`).*

| Metric | Value | vs. official starter |
|---|---|---|
| **Hit@10** | **0.880** (176 / 200) | **7.0×** (starter 0.125) |
| **MRR** | **0.4916** | **7.2×** (starter 0.068) |
| **MTTC** | **3.375 turns** | **2.9× faster** (starter 9.81 turns) |
| **TechnicalScore** | **0.7400** | **~7×** (starter 0.1067) |

---

## 1. Architecture & the simulator contract

We implemented the official Agent API exactly — and defensively. The
evaluator is imported unmodified (zero edits, imports only).

**The simulator contract**

1. **Every turn** — message + optional clarification ask + up to 10 recommendations.
2. **Zero hit sacrifice** — a clarification question never forfeits the hit check.
3. **Defensive by default** — strict dedupe, valid catalog ASINs only, spec-enum asks.
4. **Deterministic core** — offline execution; 332 automated tests guard the contracts.

**Production execution funnel**

1. **50,000-item catalog** — SQLite FTS5 BM25 + hashed TF-IDF index.
2. **Hybrid pool · ~300 items** — Reciprocal Rank Fusion (k=60) + guarantee pool.
3. **Full scoring · 320 cap** — cap ≥ pool → 100% of candidates scored.
4. **8-gate clarification** — entropy set-splitting on a Boolean token index.
5. **Top-10, attributed** — coverage × IDF × salience + popularity.

---

## 2. The staircase: 7× the official baseline

*Official metrics, public-200.*

| Metric | Starter (official) | v2 (pre-experiments) | **Shipped (freeze)** |
|---|---|---|---|
| Hit@10 | 0.125 | 0.870 | **0.880** |
| MRR | 0.068 | 0.4455 | **0.4916** |
| MTTC | 9.81 | 3.465 | **3.375** |
| TechnicalScore | 0.1067 | 0.7193 | **0.7400** |

**MTTC 9.81 → 3.38 turns — target found 2.9× faster.**

**Where the final Δ +0.0207 TechnicalScore came from** (vs. our own
pre-experiment system): MRR **+0.0138 (67%)** · Hit@10 **+0.0050 (24%)** ·
Efficiency **+0.0018 (9%)**. Two-thirds of the gain is MRR — the ranker puts
the target higher in the Top-10, exactly what the shipped change predicts.

**Official formula:**

```text
TechnicalScore = 0.5·Hit@10 + 0.3·MRR + 0.2·clip((11 − MTTC)/10)
```

---

## 3. Innovation directions: what shipped, what died

We attempted every applicable direction on the organizer's own list.

**Shipped — kept by the gates**

| Direction | What it is | Result |
|---|---|---|
| Hybrid retrieval | BM25 (0.7) + semantic TF-IDF (0.3) + RRF fusion | 88% pool recall · 0.880 Hit@10 |
| Constraint reweighting | Buying-route salience 0.5 → 0.2, popularity untouched | +1.0pp Hit · +4.6pp MRR · **SHIPPED** |
| Explainable ranking | Coverage · IDF · salience · popularity per item | Live in demo · zero score penalty |

**Killed — by their own pre-registered bars**

| Direction | What was tried | Result |
|---|---|---|
| LLM reranking tier | 3 sizes & classes probed — 2.6B dense · 30B-A3B · 120B-A12B MoE | ΔHit 0 · ΔMRR −0.005 · +2.2–8.3 s per call → killed; a local LLM loses on TTFT too |
| Soft personalization | Profile boost, weight sweep 0.00–0.15 | 0.03 worsened MRR → set to 0.00 |
| Late-phase question gate | Margin-gain question value on misses | 0 / 19 misses qualified → stopped |

Our deterministic path answers in 330 ms; LLM probes cost 2.2–8.3 s per call
for zero accuracy gain.

---

## 4. Method: pre-registered, paired, isolated

1. **Worktree isolation** — 5 isolated experiment worktrees branched from
   control `80eee9a`; frozen evaluator; zero contamination.
2. **Pre-registered bars** — pass bar written before the first eval ran:
   ΔHit ≥ +0.03 · p95 latency ≤ +2 s; automatic revert on regression.
3. **Paired-session flips** — unit of truth is per-session flips; noise floor
   ±1 session (159/160 agree); aggregate shifts < 3pp are noise.

---

## 5. The shipped win: salience vs popularity

**Paired flip waterfall (dev-160):** control **141** → **+4** miss→hit
(sessions 0031 · 0100 · 0085 · 0125) → **−1** hit→miss (session 0035) →
shipped **144**. Net +3 > ±1 noise floor.

- **Mechanism:** popularity crowded out products satisfying rare, high-value
  constraints. Fix: buying-route salience weight **0.5 → 0.2**.
- **Honesty:** the win failed its own Buying-specific hypothesis — the wins
  were route-general. It shipped anyway: the flips, not the hypothesis, were
  the evidence.
- **Confirmation (public-200):** Hit **0.870 → 0.880** · MRR **0.4455 → 0.4916**.

---

## 6. Out-of-sample confirmation

The salience gain was not overfitted to dev.

| Split | Hit@10 | Detail |
|---|---|---|
| **DEV-160** (tuning set) | **0.900** | 144 / 160 · MRR 0.5144 · MTTC 3.19 |
| **PUBLIC-200** (confirmation, touched 2×) | **0.880** | 176 / 200 · MRR 0.4916 · MTTC 3.375 |

**Hit@10 by scenario (public-200)** — exact counts shown so small
denominators stay visible:

| Scenario | Hit@10 | MRR | MTTC |
|---|---|---|---|
| Browsing | 0.9250 (74 / 80) | 0.4532 | 2.91 turns |
| Buying | 0.9125 (73 / 80) | 0.5444 | 2.65 turns |
| Intent Override | 0.7667 (23 / 30) | 0.4960 | 5.47 turns |
| Boundary (vague) | 0.6000 (6 / 10) | 0.3625 | 6.60 turns |
| **Overall** | **0.8800 (176 / 200)** | **0.4916** | **3.375 turns** |

---

## 7. The graveyard: 6 rejected by their own bars

Net paired flips (dev-160) — every red row was rejected by criteria written
before the experiment ran:

| Experiment | Flips | Verdict | Action |
|---|---|---|---|
| `exp/rank-salience` | **+3** | Exceeded ±1 noise floor · confirmed on public-200 | **MERGED** |
| `exp/global-salience` | +1 | Within ±1 noise floor · didn't generalize | Reverted |
| `exp/competition-window` | +1 | Within ±1 noise floor · identical flips | Unmerged |
| `exp/uninformative-stop` | −1 | Regressed hits · broke session 0104 | Reverted |
| `exp/rank-coverage-idf` | 0 | Pool lever never fires on dev (0/0 flips) | Unmerged |
| `exp/question-margin` | 0 / 19 | Pattern absent in the 19 misses | Stopped |
| `exp/boundary-override` | 0 | Premise disproven by replay forensics | Stopped |

*Six negatives is how you know the green one is real. The 0.90625 in our
logs was never merged.*

---

## 8. Four structural findings from negative results

1. **MTTC = first-hit turn** (miss = 11) — the evaluator stops the moment the
   target enters Top-10. Wasted questions happen post-hit; only surfacing
   sooner moves MTTC.
2. **Dialogue and retrieval are coupled** (session 0104) — stopping
   clarification changed the message stream and broke retrieval.
   "Hit-safe by construction" is false.
3. **Scenario labels ≠ runtime route** (89%) — 84 / 94 non-buying sessions
   run buying-route turns, including every one of the 15 dev misses.
4. **Re-ordering is saturated** (+2/−1 ×2) — two independent ranker changes
   produced identical flips. Remaining misses need *new information*, not
   permutations.

---

## 9. Why we miss: forensic audit of all 16 dev misses

We audited our own pipeline for leaks and found none.

| Cause | Count | Meaning |
|---|---|---|
| **Rank-depth** | 13 | Target in the pool but outranked — needs new user information, not re-ordering |
| **Pool-depth** | 2 | Target ranked 201+ in the pool — a recall cap, not a filter bug |
| **Extraction** | 1 | Complex overlapping-syntax edge case (public_0117) |

**Query faithfulness: 0 of 13 recoverable constraints dropped.** The pipeline
leaks nothing — the remaining misses are genuine capability limits, and we
know exactly which.

---

## 10. Feasibility: zero tokens, zero cost, zero network

| LLM tokens | Model cost | Network | Turn latency |
|---|---|---|---|
| **0** (0 prompt · 0 completion) | **$0.00** | **None** — fully offline at inference | **330 ms p50 · 527 ms p95** |

- **Runtime model:** deterministic BM25 + hashed TF-IDF + constraint ranker —
  no model at inference.
- **Evidence:** `results.json` → `reported_token_usage = 0` · `total_tokens = 0`.
- **Optional LLM tier:** built and gated **off** by default
  (`enable_llm_reranker = false`).
- **Environment:** Python 3.13 · Windows 11 Pro · AMD Ryzen 7 · 32 GB RAM.
- **Recorded live:** `docs/final-eval-record.md` — same frozen commit `46e3322`.

---

## 11. Business impact: from bounce to checkout

Commercial conversational search fails when users abandon: **9.8 turns to
conversion is a bounce; 3.4 is a checkout.**

- **Bounce → checkout** — 3.4 turns vs 9.8 turns completes the purchase
  instead of abandonment.
- **Attributable ranking** — every card shows coverage, IDF rarity, salience,
  popularity: math, not a black box.
- **Zero marginal cost** — 330 ms responses, $0.00 per turn, 100% uptime SLA —
  unit economics survive scale.

---

## 12. Final-eval readiness: 800 hidden sessions

- **Evaluator frozen** — byte-identical to the starter package (imports only).
- **Fresh-clone rehearsal** — a clean clone reproduces the exact 0.880 table.
- **No hardcoding** — zero session-id checks anywhere in the codebase.
- **Data isolation** — 800 hidden sessions touched 0 times · public-200 touched 2×.
- **332 automated tests** — pass in 21 s on the frozen commit.
- **Snapshot retained** — commit `46e3322` · pip deps · hardware captured.

---

## 13. Roadmap: attack the measured ceilings

| Phase | Direction | Target |
|---|---|---|
| **1** | **Recall expansion** — category-specialized inverted sub-indices break the rank-201+ candidate cap | removes the 2 pool misses |
| **2** | **Deep feature enrichment** — extract fine-grained attributes (fabric weight, collar, sole stiffness) | feeds the 13 rank-depth misses |
| **3** | **Early hit prioritization** — optimize turn-1 ranking for Top-1 placement, not just Top-10 membership | MTTC 3.38 → < 2.5 |

---

## 14. Provenance & reproducibility

**Tag chain**

```text
fork-point            80eee9a   dev baseline
new-baseline          46e3322   post-salience control
submission-freeze     46e3322   official submission
```

**Key artifacts:** `results.json` (public-200 · 0.880) ·
`runs/control-dev-newbaseline.json` (dev-160 · 0.900) ·
`docs/experiment-ledger.md` (every run) · `DATA_ATTRIBUTION.md`.

**Reproduce from a clean clone:**

```bash
# 1 · install + build catalog index
pip install -r requirements.txt
python scripts/setup_catalog.py

# 2 · test suite (332 passed)
python -m pytest -q

# 3 · official evaluator → the 0.880 table
python -m evaluator.local_evaluator

# 4 · live interactive demo
python scripts/interactive_demo.py
```

**Data attribution:** Amazon Reviews 2023, McAuley Lab, UCSD — see
[`DATA_ATTRIBUTION.md`](../DATA_ATTRIBUTION.md).

---

## About this folder (frontend demo shell)

This is the **NeeShops concept prototype**: an editorial, Pinterest-style
customer experience plus a developer dashboard for inspecting the AI
pipeline. It exists for:

- concept demonstration and the hackathon presentation
- manual click-through testing
- future visualisation of what `neeshops/agent.py` is doing (run
  inspector, experiment lab, etc. — currently populated with illustrative
  sample data, not live pipeline output)

**The official competition Agent (`starter/agent.py` → `neeshops/agent.py`)
runs entirely independently of this folder and must remain fully usable
without it.** Nothing here should ever be imported by `neeshops/` or
`starter/`.

### Files

| File | What it is |
|---|---|
| `neeshops-prototype.html` | The rendered, clickable prototype |
| `Main.dc.html` | Design-canvas source for the prototype |
| `canvas.json` | Canvas layout manifest for the design source |

### Scope notes

This folder is intentionally a demo shell — no payment, checkout, auth,
shipping, cart, or order management, none of which are relevant to the
Shopping Copilot competition. Wiring it up to live `neeshops/agent.py`
responses (e.g. via a small local API) is future work for Workstream 5 — see
`docs/neeshops/TEAM_WORKSTREAMS.md`. The agent's own live diagnostics demo
(`scripts/interactive_demo.py`, `http://127.0.0.1:8787`) serves the
production funnel and provenance tiles separately.
