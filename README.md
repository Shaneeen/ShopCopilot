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

**Start here**: `docs/neeshops/PROJECT_OVERVIEW.md` (living status +
architecture diagrams) → `docs/neeshops/TRACK4_REQUIREMENTS.md`
(competition source of truth) → `docs/neeshops/FOLDER_GUIDE.md` (what
every folder is for) → `docs/neeshops/TEAM_WORKSTREAMS.md` (the 5-person
job split) → `docs/neeshops/INTEGRATION_CONTRACTS.md` (module boundaries).

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
```

## Team workstreams

Six streams (with Person 3 split into 3A Ranking Core and 3B Personalisation & Evaluation), each owning its own module folder to minimise merge
conflicts: conversation & agent intelligence, retrieval & search, ranking
core, personalisation & evaluation, research agent & evaluation, and integration/demo/DX.
Full breakdown: `docs/neeshops/TEAM_WORKSTREAMS.md`.

## Status (v2 restructure 2026-08-30 — recall-first guarantee pool)

*Scores — official evaluator (200 public sessions, 50k catalog, `results.json`).*

| Suite | Metric | **v2 (2026-08-30)** | 08-29 rework (prev) | Organiser weak |
|---|---|---|---|---|
| **Public set** (official evaluator) | Hit@10 / MRR / MTTC / Technical | **0.870 / 0.4455 / 3.465 / 0.7193** | 0.805 / 0.402 / 3.93 / 0.665 | 0.125 / 0.068 / 9.81 / 0.107 |
| By scenario (HR@10) | buying / browsing / intent-override / boundary | **0.875 / 0.900 / 0.800 / 0.800** | 0.913 / 0.725 / 0.800 / 0.60 | — |

The v2 restructure (`docs/IMPLEMENTATION_V2.md` for the full decision log): an exact
Boolean-AND **guarantee pool** over a new in-memory token index (the simulator's
constraint values are verbatim tokens of the target's own text, so the AND set
contains the target by construction — pool membership ~84% of scored turns),
coverage×IDF×salience ranking with minmax-normalized retrieval, gates-not-caps
clarification with a hard turn-guard (recommendations on EVERY turn; no questions
after turn 9), over-generality detection → set-splitting questions, stale-slot +
inferred-attribute state lifecycle, fast token-set filters, and the instrumentation
panel with per-session miss decomposition. Tests: **248 passed, 1 deselected**.

## Status (staging-main 2026-08-29 — P2+P3 integrated)

*Branches:* `main` (organiser) → `staging-main` pre-synced → `yu_le_p2`
(retrieval strategies, RRF, provenance, deterministic merge, demo diagnostics)
+ `shaneen-Person3_combined` (constraint-aware ranking R2/R3, personalization,
LLM reranker Gemini/fake). Merge unions: `.gitignore` (P2 semantic ignores +
P3 `.obsidian`) / `requirements.txt` (`numpy` + `google-genai`). Full suite
**162 passed, 1 deselected** (after the 08-29 rework); oracle `30/7` reproduces
§1; readiness all PASS.

*Scores — official evaluator (200 public sessions, 50k catalog, `results.json`).
Baseline references: organiser weak starter `0.125/0.068/9.81/0.107`; NeeShops
2026-08-28 initial `0.285/0.189/8.55/0.248` (see
`docs/neeshops/PROJECT_OVERVIEW.md`).*

| Suite | Metric | 2026-08-29 rework (current) | staging-main 08-29 (prev) | Organiser weak |
|---|---|---|---|---|
| **Public set** (official evaluator, 200 sessions) | Hit@10 / MRR / MTTC / Technical | **0.805 / 0.402 / 3.93 / 0.665** | 0.49 / 0.284 / 7.25 / 0.405 | 0.125 / 0.068 / 9.81 / 0.107 |
| By scenario (HR@10) | buying / browsing / intent-override / boundary | **0.913 / 0.725 / 0.800 / 0.60** | 0.40 / 0.513 / 0.633 / 0.60 | — |
| **Oracle** (random catalog targets, 30/7) | Hit / MRR / MTTC · Pool@200 | **0.767 / 0.389 / 3.90 · 68.2%** | 0.600 / 0.239 / 5.77 · 14.3% | — |
| **Bench v1.0** (100 cases, no-LLM, seed 7) | hard / insane hit | **0.933 / 0.340** | 0.833 / 0.240 | — |

The 2026-08-29 rework: wildcard-first clarification (`other` questions whose
compound answers yield 2 constraints/turn), 3-angle multi-query RRF retrieval
(target-in-pool@200 14.3% → 68.2%), demote-not-drop metadata filters
(filter-killed-target → 0), and `ConstraintAwareRanker` wired as the default
ranker — stage-by-stage rationale in `docs/archive/p2readme.md §7b`, bench before/after in
`evaluation/BENCH_V1.0.md §5.1`. Tests: **162 passed, 1 deselected**.
Latency 60–270 ms/turn ≪ budget.
