# ShopCopilot — TikTok TechJam 2026

> **Track 4 · Conversational E-Commerce Search · 50k catalog · 10 turns max · deterministic · $0 LLM cost**

> **Our Scores (public-200, `results.json`): Hit@10 0.880 · MRR 0.4916 · MTTC 3.375 · Efficiency 0.7625 · TechnicalScore 0.7400**

## Benchmarks

| Metric | Starter | **ShopCopilot (Submission)** | Δ |
|---|---|---|---|
| **Hit@10** | 0.125 (25/200) | **0.880 (176/200)** | **7.0×** |
| **MRR** | 0.0680 | **0.4916** | **7.2×** |
| **MTTC** | 9.81 | **3.375** | **2.9× faster** |
| **TechnicalScore** | 0.1067 | **0.7400** | **~7×** |
| **Cost / Tokens** | 0 | **$0.00 · 0 tokens** | deterministic |
| **Latency** | ~200ms | **p50 330ms · p95 527ms** | offline |

### Per-Scenario (public-200)

| Scenario | Hit@10 | MRR | MTTC |
|---|---|---|---|
| **Browsing** (80) | **0.9250** (74/80) | 0.4532 | 2.91 |
| **Buying** (80) | **0.9125** (73/80) | 0.5444 | 2.65 |
| **Intent Override** (30) | **0.7667** (23/30) | 0.4960 | 5.47 |
| **Boundary** (10) | **0.6000** (6/10) | 0.3625 | 6.60 |
| **Overall** | **0.8800** | **0.4916** | **3.375** |

> Formula: `TechnicalScore = 0.5·Hit + 0.3·MRR + 0.2·clip((11-MTTC)/10)` · 332 tests · `evaluator/local_evaluator.py` on 50k Clothing catalog

## Deck & Docs

- **Deck PPTX:** [docs/presentation/ShopCopilot_TechJam_Deck.pptx](docs/presentation/ShopCopilot_TechJam_Deck.pptx)
- **Deck PDF:** [docs/presentation/ShopCopilot_TechJam_Deck.pdf](docs/presentation/ShopCopilot_TechJam_Deck.pdf)
- **Ledger (experiments + forensics):** [docs/experiment-ledger.md](docs/experiment-ledger.md)
- **Fresh-clone audit:** [docs/final-eval-record.md](docs/final-eval-record.md)
- **Architecture:** [docs/neeshops/ARCHITECTURE.md](docs/neeshops/ARCHITECTURE.md)
- **Solution Report:** [docs/neeshops/SolutionReport.md](docs/neeshops/SolutionReport.md)

## Flow — How It Works

**Thesis:** *Best agent maximizes information per turn, not retrieval per turn.* Questions chosen by exact set-splitting entropy on an in-memory inverted index.

```
evaluator → starter/agent.py (contract) → neeshops/agent.py
  → conversation (state → intent → constraints → 8-gate clarification)
  → retrieval (TokenIndex AND + BM25 FTS5 + semantic hashed TF-IDF → hybrid RRF k=60 → guarantee pool 300)
  → ranking (coverage×IDF×salience, violations first, full-pool 320) → recommend + provenance
```

1. **Contract** — 10 turns, `ask_attribute` ∈ {category,material,color,size,style,brand,budget,feature,use_case,other,null} + top-10 recommendations.
2. **Staircase** — 0.125 → 0.870 (v2 guarantee pool + constraint rerank) → **0.880** (+4/−1 salience 0.5→0.2) — 67% of ΔTech from MRR.
3. **Shipped vs Killed** — shipped: hybrid RRF, guarantee pool, 8-gate set-splitting, stale/inferred state; killed: personalization weight sweep (0.00), LLM rerank (Δ0, +454ms), stop-rules — 6 negatives preserved in ledger.
4. **Miss map** — 16 dev misses = 13 rank-depth + 2 pool (cap) + 1 extraction + 0 dropped constraints.
5. **Feasibility** — deterministic, offline, 0 tokens, p50 330ms, 332 tests.

## Clone & Setup

```bash
git clone https://github.com/Shaneeen/ShopCopilot.git
cd ShopCopilot

python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # only if you enable LLM reranker (off by default)

python scripts/setup_catalog.py          # builds data/catalog.fts.db (92MB, 50k)
python scripts/build_semantic_index.py   # optional — builds data/semantic.index.npy
python scripts/create_dev_split.py       # 160 dev / 40 holdout (seed 7)
```

Requires `data/catalog.jsonl` — download `catalog.jsonl.gz` from GitHub Release → `gzip -dk catalog.jsonl.gz && mv catalog.jsonl data/catalog.jsonl` (verify `SHA256SUMS`). Python 3.10+ (tested 3.13).

## Repository Layout

```
ShopCopilot/
  evaluator/local_evaluator.py   # frozen official simulator — never edit
  starter/agent.py               # ~30-line adapter (delegates to neeshops/)
  neeshops/
    agent.py                     # orchestration only
    conversation/                # state, intent, constraints, 8-gate clarification
    retrieval/                   # bm25, semantic, hybrid, TokenIndex guarantee pool
    ranking/                     # deterministic + LLM-gated reranker
    personalization/             # soft boost (weight 0.15 → swept 0.00)
    config/default_strategy.json # single source of tunable weights
    models/ utils/ research/
  scripts/                       # setup_catalog, instrumented_eval, bench_v1, interactive_demo, etc.
  docs/
    experiment-ledger.md         # metrics matrix
    final-eval-record.md         # fresh-clone rehearsal
    neeshops/ARCHITECTURE.md     # pipeline diagram
    presentation/                # ShopCopilot_TechJam_Deck.pptx/.pdf
  tests/                         # 332 tests (pytest -q)
  data/                          # gitignored — built locally
  runs/                          # control-dev-newbaseline.json + dev-*.json snapshots
frontend/                        # decoupled demo prototype (not part of Agent)
```

See [docs/neeshops/ARCHITECTURE.md](docs/neeshops/ARCHITECTURE.md) for module contracts.

## Run Tests & Reproduce

```bash
# tests
pytest -q                          # 332 passed, 1 deselected

# official score (200 public)
python -m evaluator.local_evaluator        # → results.json 0.880 / 0.4916 / 3.375

# instrumented panel (dev-160) + forensics
python scripts/instrumented_eval.py --output evaluation/results/instrumented_results.json
python scripts/pool_miss_forensics.py --cases 160 --seed 7

# benches
python scripts/bench_v1.py --cases 100 --workers 1 --arms no-llm
python scripts/run_experiment.py --random 3

# live demo
python scripts/interactive_demo.py        # http://127.0.0.1:8787 — funnel, provenance, sampled replay
```

All tuning on `data/dev_split.jsonl` (160) — public-200/holdout are confirmation only. Every new key in `default_strategy.json` must be in `research/experiment.py::SAFE_PARAMETERS` (`test_config_registered.py`).

## Team Contributions — ANYTHING AH

- **Yu Le** — Project core architecture, hybrid retrieval & ranking experiments, overall pipeline orchestration, evaluation and deck.
- **Shaneen** — Ranking & personalization; deterministic ranker and LLM reranking layer, personalization scoring and experiments.
- **Gwen** — Conversational understanding; intent routing, constraint extraction, state tracking and clarification strategy.
- **Darius** — Research infrastructure & optimization; experiment tooling and **Demo Video / presentation**.
- **Clarence** — Integration & reliability; Agent contract, test harness and end-to-end reliability.

## Limitations & Future Work

- 4-case LLM probe only (ΔHit 0, ΔMRR −0.005, +2.2–8.3s); full 20/100-case Nemotron validation not yet completed — see `docs/experiment-ledger.md` §6 for details.
- 16 dev-160 misses remain (13 rank-depth, 2 pool-cap, 1 extraction) — ceiling 0.900 Hit without deeper retrieval.
- In-memory hashed TF-IDF, not transformer embeddings — swap-in `sentence-transformers` kept as opt-in (`requirements.txt:32`).
- Next: larger LLM probe, boundary-scenario retrieval floor tuning, and holdout-40 confirmation.

## Attribution

Catalog & sessions derived from Amazon Reviews 2023 (McAuley Lab, UCSD).

*ShopCopilot — TikTok TechJam 2026 · Team ANYTHING AH · deterministic · reproducible*
