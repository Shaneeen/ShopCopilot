# Track 4 Requirements — Internal Source of Truth

**TikTok TechJam 2026 — Track 4: Shopping Copilot: AI Conversational
Search and Recommendations.** Official repo:
`https://github.com/TechJam2026/techjam-conversational-search`.

> **If any NeeShops idea, doc, or code conflicts with this document or
> with the official participant repository, the official competition
> requirements take priority.** This file is a summary for the team, not
> a replacement for `docs/competition_specification.md`,
> `docs/agent_api_contract.json`, `docs/evaluation_config.json`, or
> `docs/baseline_results.json` (all official, unmodified, in this repo).

## Challenge objective

Build a conversational shopping Agent that, across at most 10 turns,
finds a hidden target product and returns it as early and as highly
ranked as possible in a Top-10 list — while asking useful (not random)
clarifying questions along the way. This is a **backend/headless AI Agent
challenge**, not a frontend/UI competition.

## Core requirement 1 — Buying vs Browsing routing

- **Buying**: high-intent, harder constraints ("black waterproof running
  shoes under $120"). Favours hard filters, precise constraints, category
  matching, keyword/BM25, metadata filtering, efficient convergence.
- **Browsing**: open-ended, exploratory ("something nice for a casual
  weekend"). Favours semantic retrieval, broader exploration, preference
  interpretation, clarification, diverse recommendations.
- Architecture must support different retrieval/ranking strategies per
  route (config-driven weights, not hardcoded).

## Core requirement 2 — Hybrid retrieval

Combine keyword/BM25, category retrieval, metadata filtering, dense/vector
retrieval, rule-based retrieval, semantic reranking, local scoring, and
optionally LLM reranking. **Keep retrieval lightweight/in-memory** — no
external vector database infrastructure.

## Core requirement 3 — Multi-turn conversation state

Must accumulate across turns: known preferences, explicit constraints,
asked attributes, previous recommendations, user profile, conversation
history, no-preference values.

## Core requirement 4 — Intent Override

A new explicit value replaces the old one outright.

```text
color = blue  →  "Actually forget blue, I want black."  →  color = black
```

Never `blue + black` unless both were genuinely requested. **This is a
specifically evaluated scenario** (15% of the official mix).

## Core requirement 5 — Boundary behaviour

"I don't have a colour preference" → `color = NO_PREFERENCE`, and the
Agent must never ask about that attribute again in the session. 5% of the
official mix.

## Core requirement 6 — Clarification strategy

Each turn may ask a question, return recommendations, or both. Question
choice should eventually weigh: missing important constraints,
candidate-set size, information gain, scenario type, already-asked
fields, remaining turns, user-profile info. Asking randomly/excessively is
penalised because **efficiency (MTTC) is scored**.

## Core requirement 7 — Dynamic context / personalisation

The official profile provides `purchase_frequency`, `average_prior_rating`,
`rating_style`, `preference_tags`, `summary`. These are **soft signals
only** — they must never override an explicit current request (e.g.
profile says "comfort, durability, fit" but the user asks for "lightweight
fashion sneakers" → the active request wins).

## Official competition data

- **Catalog**: 50,000 Amazon products, `Clothing_Shoes_and_Jewelry`.
  Fields include `parent_asin`, `title`, `features`, `description`,
  `price`, `categories`, `details`, `average_rating`, `rating_number`,
  `store`. **Read-only** — never mutate records, insert fake products, or
  score against ASINs outside the official catalog.
- **Public development sessions**: 200 labelled, for dev/eval/debugging
  (`data/public_set.jsonl`, official, committed).
- **Private evaluation**: 800 hidden sessions, unseen until final judging,
  separate users/targets from the public set — **do not blindly optimise
  against all 200 public cases**; use a reproducible internal
  development/holdout split (`scripts/create_dev_split.py`).
- **Official scenario mix** (inspect metrics overall *and* per-scenario):
  40% Buying, 40% Browsing, 15% Intent Override, 5% Boundary.

## Participant resources

- **Weak BM25 starter Agent** — originally `starter/agent.py`; intentionally
  weak, explicitly modifiable/replaceable. NeeShops replaced its body with
  a thin adapter into `neeshops/` (see `docs/neeshops/ARCHITECTURE.md`) —
  the constructor signature and contract shape are unchanged.
- **Deterministic local evaluator** — `evaluator/local_evaluator.py`.
  **Never modify it to improve reported results.** Run via
  `python3 -m evaluator.local_evaluator` (writes `results.json` with
  aggregate + per-scenario metrics).

## Official Agent API contract

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None: ...
    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict: ...
```

Response shape (`docs/agent_api_contract.json`, `additionalProperties:
false` — extra keys are not allowed):

```python
{
    "message": "Do you have a material preference?",
    "ask_attribute": "material",
    "recommendations": [{"parent_asin": "B000..."}],   # score optional
    "usage": {"prompt_tokens": 120, "completion_tokens": 30}
}
```

Allowed `ask_attribute` values: `category`, `material`, `color`, `size`,
`style`, `brand`, `budget`, `feature`, `use_case`, `other`, or `null`. The
evaluator uses `ask_attribute` to decide what the simulated shopper
reveals next — an invalid value gets no useful reply.

## Session limit

Max **10 turns**, `top_k = 10` (a `const` in the schema — always pass/use
10).

## Official technical metrics

- **Hit Rate@10** — fraction of sessions where the target appears in the
  scored Top 10. Higher is better.
- **MRR** — mean reciprocal rank (1.0 / 0.5 / 0.333... by rank; miss = 0).
  Higher is better.
- **MTTC** — mean turns to conversion; a miss counts as turn 11. Lower is
  better.
- **Efficiency** = `clip((11 - MTTC) / 10, 0, 1)`.
- **Technical Score** = `0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency`.

Priority order this implies: **(1) find the right product, (2) rank it
highly, (3) find it quickly.** Do not optimise solely for conversational
sophistication.

## Official baseline (weak BM25 starter, `docs/baseline_results.json`)

```text
Hit Rate@10:    0.125
MRR:            0.068034
MTTC:           9.81
Efficiency:     0.119
TechnicalScore: 0.10671
```

**First meaningful milestone: `TechnicalScore > 0.10671` on the official
public evaluation, actually measured — never invented.**

## Judging weights (final event)

| Criterion | Weight | Judges look for |
|---|---|---|
| Technical Execution | 35% | engineering fundamentals, architecture, reliability |
| Innovation & Problem Insight | 20% | originality, problem understanding, approach selection |
| Impact & Relevance | 20% | real-user value, applicability beyond the hackathon |
| Feasibility & Practicality | 15% | realistic scope, resource usage, sustainable approach |
| Presentation & Communication | 10% | clear story, technical understanding, Q&A |

## In scope

Buying/Browsing intent detection, heterogeneous retrieval routing, dynamic
retrieval weights, dynamic candidate truncation, slot/state decay, adaptive
memory, personalised context, prompt/ranking strategy refinement, local
scoring, keyword/dense/hybrid retrieval, reranking, local models, external
model APIs.

## Out of scope (do not prioritise)

- **UI/UX development** — evaluated via backend/headless execution. The
  NeeShops frontend (`frontend/`) is an optional demo shell only — see
  `docs/neeshops/PROJECT_OVERVIEW.md` and Part J below.
- **Full-parameter foundation model training.**
- **Heavy external vector infrastructure** — prefer lightweight/in-memory.
- **Multimodal processing** — image/video product search, AI-media
  detection are explicitly out of scope for Track 4. They live only as
  documented future ideas in `neeshops/experimental/README.md` and must
  never block or affect the official Agent path.

## External model policy

The organiser provides **no** hosted models, API keys, tokens, or credits.
Teams own their own credentials, cost, usage limits, latency, and secret
handling. **API secrets must never be committed** — use environment
variables (`.env`, gitignored; `.env.example` documents the shape). A paid
LLM is not mandatory.

## Required final deliverables

1. **Written project description** — how NeeShops solves the challenge,
   tools/APIs/frameworks/data used.
2. **Public Git repository** — organised code, commented components,
   README with install/setup/reproduction/limitations/future
   work/contributions.
3. **Demo video** — end-to-end: API interaction, evaluator, inference
   results, developer dashboard/metrics/Agent trace acceptable. A full
   shopping frontend is not required.
