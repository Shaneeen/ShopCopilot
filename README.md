> **Our Scores (public-200, `results.json`): Hit@10 0.88 · MRR 0.4916 · MTTC 3.375 · Efficiency 0.7625 · TechnicalScore 0.7400**

# ShopCopilot — Conversational E-Commerce Search (TikTok TechJam 2026)

> **Start here:** `docs/experiment-ledger.md` — metrics matrix + run inventory; `docs/final-eval-record.md` — fresh-clone audit. Parent directory should contain **only** `ShopCopilot/` (worktrees removed 2026-08-31, branches tagged `archive/exp-*`).

## Status (2026-08-31 — Submission Freeze: `46e3322`)

*Official Evaluator Scores (`evaluator/local_evaluator.py`, 200 public sessions, 50,000 catalog items, freeze tag `submission-freeze`).*

| Metric | Official Starter Baseline | Pre-Experiments (v2 Baseline) | **Final Shipped (`submission-freeze`)** | Δ vs Starter |
|---|---|---|---|---|
| **Hit@10** | 0.1250 (25/200) | 0.8700 (174/200) | **0.8800 (176/200)** | **7.0× (+75.5 pp)** |
| **MRR** | 0.0680 | 0.4455 | **0.4916** | **7.2× (+0.4236)** |
| **MTTC** | 9.81 turns | 3.465 turns | **3.375 turns** | **2.9× faster (−6.435 turns)** |
| **TechnicalScore** | 0.1067 | 0.7193 | **0.7400** | **~7× (+0.6333)** |
| **LLM Tokens / Cost** | 0 / $0.00 | 0 / $0.00 | **0 / $0.00 (Deterministic)** | $0.00 API cost |
| **Turn Latency (dev-160)** | ~200 ms | ~230 ms | **p50: 330.1 ms · p95: 526.6 ms** | Sub-400ms SLA |

### Per-Scenario Performance Breakdown (Public-200)

| Scenario | Sample Count | Hit@10 | MRR | MTTC |
|---|---|---|---|---|
| **Browsing** | 74 / 80 (92.5%) | 0.9250 | 0.4532 | 2.91 turns |
| **Buying** | 73 / 80 (91.25%) | 0.9125 | 0.5444 | 2.65 turns |
| **Intent Override** | 23 / 30 (76.7%) | 0.7667 | 0.4960 | 5.47 turns |
| **Boundary (Vague)** | 6 / 10 (60.0%) | 0.6000 | 0.3625 | 6.60 turns |
| **Overall** | **176 / 200 (88.0%)** | **0.8800** | **0.4916** | **3.375 turns** |

### Submission Deliverables & Documentation
- **Presentation Deck (PPTX):** [docs/presentation/ShopCopilot_TechJam_Deck.pptx](docs/presentation/ShopCopilot_TechJam_Deck.pptx)
- **Presentation Deck (PDF):** [docs/presentation/ShopCopilot_TechJam_Deck.pdf](docs/presentation/ShopCopilot_TechJam_Deck.pdf)
- **Fresh-Clone Rehearsal & Compliance Audit:** [docs/final-eval-record.md](docs/final-eval-record.md)
- **Experiment Ledger:** [docs/experiment-ledger.md](docs/experiment-ledger.md)
- **Architecture & Retrieval/Ranking Detail:** [docs/neeshops/ARCHITECTURE.md](docs/neeshops/ARCHITECTURE.md) *(public summary for Technical Report)*
- **Claim-to-Evidence / Speaker & Video Scripts:** private — see `Experiment Ledger` + `final-eval-record` for public evidence; deck above is the pushed presentation

### Quickstart & Reproduction
```powershell
# 1. Install Dependencies & Build Catalog FTS Database
pip install -r requirements.txt
python scripts/setup_catalog.py

# 2. Run Test Suite (332 passed, 1 deselected)
python -m pytest -q

# 3. Reproduce Official Evaluator Table (Hit@10 0.880, MRR 0.4916)
python -m evaluator.local_evaluator

# 4. Launch Interactive Live Demo (with Sampled Session Replay & Provenance Chips)
python scripts/interactive_demo.py
```

---

# TechJam Conversational E-Commerce Search Challenge




Build an AI shopping agent that asks useful follow-up questions and recommends the customer's hidden target product within at most 10 turns.

## What You Receive

- A frozen catalog of 50,000 products from the `Clothing_Shoes_and_Jewelry` category of Amazon Reviews 2023.
- 200 labeled public sessions for local development.
- A weak BM25 starter agent and deterministic local evaluator.
- The Agent API contract and scoring rules.

The organizer keeps 800 additional sessions private for final evaluation.

## Task

For each session, your agent receives an anonymized preference profile and a short customer message. Raw user IDs, review text, timestamps, and purchase history are never disclosed. On every turn the agent may:

- ask a natural clarification question in `message` and identify one requested field in `ask_attribute`;
- return a ranked list of up to 10 catalog `parent_asin` values;
- do both in the same response.

The session ends when the target product appears in the scored Top 10 or after turn 10. Sessions cover Buying, Browsing, Intent Override, and Boundary behavior.

## Download the Catalog

Download `catalog.jsonl.gz` from the GitHub Release attached to this repository, then run:

```bash
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
```

Verify the downloaded file using the published `SHA256SUMS` file.

## Run the Starter

Python 3.10 or later is recommended. The starter uses only the Python standard library.

```bash
python3 -m evaluator.local_evaluator
```

Edit `starter/agent.py` to implement your system. Do not edit the evaluator or public labels when reporting your local score.
The command writes per-session results and aggregate metrics to `results.json`.

The included weak BM25 starter scores Hit Rate@10 `0.125`, MRR `0.068034`, and
MTTC `9.81` on the released public set. See `docs/baseline_results.json`.

## Agent Interface

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return {
            "message": "Do you have a material preference?",
            "ask_attribute": "material",
            "recommendations": [
                {"parent_asin": "B000..."},
                {"parent_asin": "B001..."}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}
        }
```

`ask_attribute` is one of `category`, `material`, `color`, `size`, `style`, `brand`, `budget`, `feature`, `use_case`, `other`, or `null`. See `docs/agent_api_contract.json`.

## Technical Metrics

- **Hit Rate@10:** fraction of sessions that find the target within 10 turns.
- **MRR:** mean reciprocal rank of the target; a miss contributes zero.
- **MTTC:** mean first-hit turn; a miss is assigned turn 11.
- **Reported token usage:** prompt and completion tokens returned by the team's model client.

```text
TechnicalScore = 0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency = clip((11 - MTTC) / 10, 0, 1)
```

Only exact `parent_asin` equality produces a hit. Core metrics are also reported by scenario.

## Model Choice and Cost

Teams may use any legally accessible LLM API or local model. Teams manage their own credentials and must never commit API keys. Model choice, estimated cost, token usage, and latency must be disclosed. Token usage is a feasibility metric, not part of the core technical score. The organizer does not provide or reimburse model API credits; teams are responsible for any costs incurred through optional external services.

## Files

```text
data/public_set.jsonl             200 labeled development sessions
docs/competition_specification.md participant rules and evaluation protocol
docs/agent_api_contract.json      machine-readable Agent contract
docs/evaluation_config.json       scoring configuration
docs/baseline_results.json        reproducible weak-starter reference score
starter/agent.py                  editable weak starter
evaluator/local_evaluator.py      public-set simulator and scorer
```

## Judging and Submission Policy

- Participant submission requirements: `docs/submission_rules.md`
- Participant release checklist: `docs/participant_release_checklist.md`
- Organizer-only final judging controls: `organizer/JUDGING_RUNBOOK.md`
- Organizer private release checklist: `organizer/private_release_checklist.md`
- Judging day operations SOP: `organizer/JUDGING_DAY_SOP.md`

## Data Source

The catalog and sessions are derived from Amazon Reviews 2023 by McAuley Lab, UCSD. See `DATA_ATTRIBUTION.md` before using or redistributing the data.
Sessions are sampled deterministically from the official Clothing 5-core leave-last-out split and joined to the frozen catalog.

---

# NeeShops implementation

Everything above this line is the organiser's official participant kit
(`TechJam2026/techjam-conversational-search`), unmodified. Everything below
documents **our team's implementation**, layered on top of it without
touching the official contract.

## What we built

`starter/agent.py` is a thin adapter (unchanged `Agent(catalog_path)`,
`reset()`, `respond()` contract) delegating to `neeshops/`: conversation
state + buying/browsing routing + adaptive clarification, **hybrid
BM25 (field-weighted, FTS5) + semantic (hashed TF-IDF + numpy cosine)**
with strategy knob (`bm25_only`/`semantic_only`/`hybrid`/`fused` RRF k=60)
and provenance-stamped merge, metadata filtering, **constraint-aware reranking
(R2/R3) + personalization boost (soft, weight 0.15) + optional LLM reranker
(Gemini/fake)**, and a controlled research/experimentation framework.
Detail: `docs/neeshops/ARCHITECTURE.md`; P2 measured gains: `docs/archive/p2readme.md`;
P3 ranking: `neeshops/ranking/README.md` + `docs/archive/person3/`.

**Start here**: `docs/neeshops/ARCHITECTURE.md` (architecture) → `docs/neeshops/TRACK4_REQUIREMENTS.md`
(competition source of truth) → `docs/neeshops/FOLDER_GUIDE.md` (what
every folder is for) → `docs/neeshops/INTEGRATION_CONTRACTS.md` (module boundaries).

## Repository layout (additions)

```text
neeshops/            our implementation — see docs/neeshops/ARCHITECTURE.md
scripts/             our setup/eval/experiment helper scripts (do not replace the official evaluator)
frontend/            a decoupled demo prototype — not part of the competition Agent, see frontend/README.md
docs/neeshops/        our architecture, team workstreams, experiment log, competition notes
```

## Setup (adds to the official steps above)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # only needed for neeshops/ — the official baseline itself is stdlib-only
cp .env.example .env              # optional, only for LLM-backed features (disabled by default)
```

## Running things

```bash
PYTHONPATH=. python -m evaluator.local_evaluator  # official scoring → results.json
pytest -q                                          # v2: 248 passed, 1 deselected
python scripts/run_oracle_eval.py --strategy both --cases 30 --seed 7  # P2 oracle A/B
python scripts/instrumented_eval.py                # v2 panel: miss decomposition, gates, latency
python scripts/pool_miss_forensics.py --cases 300 --seed 7             # recall forensics
python scripts/bench_v1.py --cases 100 --workers 1 --arms no-llm       # tier bench (workers=1: GIL-bound)
python scripts/run_baseline.py                     # fast adapter smoke check
python scripts/create_dev_split.py
python scripts/run_experiment.py --random 3
python scripts/interactive_demo.py                 # http://127.0.0.1:8787 — funnel, provenance tiles
