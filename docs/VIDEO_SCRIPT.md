# ShopCopilot — 2-Minute Demo Video Script (TechJam 2026)

**Target Duration:** Exactly 120 Seconds (2:00)  
**Format:** Screen Recording (1080p, 60fps) + Clean Voiceover  
**Live URL:** `http://127.0.0.1:8787` (`python scripts/interactive_demo.py`)  

---

## Shot-by-Shot Storyboard & Voiceover Track

### Shot 1: The Problem & Live Demo Header (0:00 – 0:18 · 18s)
- **Visual:** Browser showing `http://127.0.0.1:8787`. Zoom in on Header Banner: `config: submission-freeze (46e3322) · deterministic ranker · LLM off`.
- **Voiceover:**  
  "This is ShopCopilot. Our challenge in TikTok TechJam Track 4: surface a customer’s hidden target product from a 50,000-item catalog in 10 conversational turns. Against the official baseline of 12.5% Hit Rate, our deterministic agent reaches **88% Hit Rate** and **0.49 MRR** in just **3.4 turns** — with zero LLM API cost."
- **Pacing:** Upbeat, crisp, confident.

---

### Shot 2: Sampled Session Mode — `public_0112` (0:18 – 0:48 · 30s)
- **Visual:** Select `public_0112 — boundary · deep start · pool 195→1` from dropdown. Click **Load sampled session**.
- **Actions on Screen:**
  1. Click **Next turn ▸** (Turn 1): Agent responds with initial exploratory query.
  2. Click **Next turn ▸** (Turn 2): Customer reveals "I don't have a preference for brand". Constraint panel updates with `brand: NO_PREFERENCE (never re-asked)`.
  3. Click **Next turn ▸** through Turn 6: Watch target product climb steadily in the rank table.
  4. At Turn 6: Target product hits **#2 in top 10**. **🎯 Target in top-10 — session ends** banner appears with log-scale rank trajectory sparkline (195 → 201 → 203 → 196 → 20 → 2).
- **Voiceover:**  
  "To demonstrate real behavior, we load a curated session from the dev split, driving the official frozen evaluator live. Notice how the agent extracts the boundary condition, marks brand as 'no preference' so it's never re-asked, and collapses the candidate pool. By turn 6, the target product climbs from rank 195 to rank 2, triggering an immediate session win."
- **Pacing:** Sync clicks with voiceover phrases.

---

### Shot 3: Baseline vs Final Ranking Toggle & Provenance (0:48 – 1:15 · 27s)
- **Visual:** Scroll to the Recommendation Cards for Turn 6.
- **Actions on Screen:**
  1. Point cursor at provenance chips: `cov 1.82`, `sal 0.20`, `pop 0.44`, `pool #20 → #2`, `viol 0`.
  2. Click the **Baseline · pre-experiment** toggle button. Watch cards animate and re-sort via FLIP transition.
  3. Click **Final · shipped** toggle button to return to shipped weights.
- **Voiceover:**  
  "Every recommendation carries full ranking provenance: IDF coverage, satisfied constraint salience, popularity, and pool movement. With our live toggle, we can re-score this exact candidate pool using pre-experiment salience weights versus our shipped configuration. Notice how lowering salience weight prevents popularity from crowding out genuine constraint matches."
- **Pacing:** Click toggle on the word "toggle", re-sort animation visible.

---

### Shot 4: Diagnostics Panel & Zero-Cost Telemetry (1:15 – 1:35 · 20s)
- **Visual:** Scroll down to the **Turn diagnostics** and **Constraint state** panels.
- **Highlights on Screen:**
  - Funnel: `50,000 catalog → 284 hybrid retrieval → 284 candidate pool → 284 scored (cap 320) → top 10`.
  - Metrics tile: `turn latency 327 ms`, `session p50 330 ms`, `tokens 0`, `model cost $0.00 · deterministic — no LLM calls`.
- **Voiceover:**  
  "In our diagnostics funnel, 100% of candidate products are scored through our constraint-aware ranker. Notice our cost telemetry: zero tokens consumed, zero API cost, and a p50 turn latency of 330 milliseconds on local hardware."
- **Pacing:** Highlight metrics with mouse hover.

---

### Shot 5: Fresh-Clone Terminal Reproduction & Closing (1:35 – 2:00 · 25s)
- **Visual:** Switch to Terminal. Run `python -m pytest -q` (332 passed in 21s) followed by `python -m evaluator.local_evaluator`.
- **Action on Screen:** The official 0.880 summary table prints out on the terminal screen.
- **Voiceover:**  
  "Our entire pipeline is 100% reproducible. All 332 unit tests pass in 21 seconds. Running the official evaluator on a clean clone reproduces the exact 0.880 Hit Rate table. ShopCopilot delivers high-accuracy conversational shopping with complete transparency and zero inference cost. Thank you."
- **Pacing:** Terminal text finishes printing as voiceover concludes.

---

## Pre-Take Checklist for Recording
- [ ] Clean browser window at `1920x1080`, zoomed to 100%.
- [ ] Kill any stale servers (`netstat -ano | findstr :8787`).
- [ ] Start fresh demo instance: `python scripts/interactive_demo.py`.
- [ ] Practice the 6 clicks for `public_0112` to ensure smooth pacing.
- [ ] Terminal font set to Consolas 16pt, dark theme.
