# NeeShops Beginner Start Here

This is the first document every teammate should read. It explains what the
project does, how the pieces fit together, and how to start without assuming
you already know retrieval systems, LLMs, or multi-turn agents.

**We are not reducing the project scope.** The full plan still includes
conversation intelligence, BM25 and semantic retrieval, metadata filtering,
heuristic and LLM reranking, personalisation, controlled experimentation,
reliability work, and the Agent Trace Viewer. The purpose of this guide is to
put that work in a safe order and give every beginner a small first step.

## The project in one minute

NeeShops is a Python shopping assistant. The evaluator secretly chooses a
product from a catalog. It gives our Agent a simulated shopper message, such
as:

```text
I'm looking for women's shoes, but I'm still exploring.
```

Our Agent has at most 10 turns to:

1. remember what the shopper has said;
2. ask useful follow-up questions;
3. search 50,000 products;
4. rank up to 10 product IDs;
5. return the hidden target as early and as high in the list as possible.

Only exact `parent_asin` product IDs are scored. The frontend is useful for
the demo, but the official evaluator calls the Python Agent directly.

## Official sources

- [Participant repository](https://github.com/TechJam2026/techjam-conversational-search)
- [Participant Kit Release](https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit)
- [Amazon Reviews 2023 documentation](https://amazon-reviews-2023.github.io/)
- Local official rules: `docs/competition_specification.md`
- Local response schema: `docs/agent_api_contract.json`
- Local submission rules: `docs/submission_rules.md`

When two documents disagree, use this order:

1. official participant repository and release;
2. official files under `docs/`;
3. `docs/neeshops/TRACK4_REQUIREMENTS.md`;
4. other NeeShops planning documents.

## What is official and what is our full build scope?

The official contract says what must be accepted by the evaluator: the Agent
interface, valid responses, the 10-turn limit, exact product IDs, setup and
reproduction instructions, a short report, disclosures, and a demo.

The competition also permits and encourages approaches such as semantic
retrieval, adaptive clarification, personalisation, and optional LLM
reranking. NeeShops has chosen to implement all of these as its full team
scope. Some are not mandatory API fields, but they are still team
deliverables in this repository.

This distinction does **not** remove work. It prevents a beginner from
mistaking an implementation idea for an evaluator rule and changing the
official contract by accident.

## Setup: copy and paste these commands

Run these from the repository root.

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/download_catalog.py
python scripts/check_readiness.py
pytest -q
```

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/download_catalog.py
python scripts/check_readiness.py
pytest -q
```

`download_catalog.py` downloads the official release archive, checks the
organizer's SHA-256 value, validates 50,000 unique product IDs, and refuses to
overwrite an existing catalog.

If the readiness command prints `FAIL`, fix that line before coding. `INFO`
means an advanced optional dependency is not installed yet; the owning
workstream will add it when implementing that component.

## The data flow in plain English

```text
Evaluator
  -> starter/agent.py        checks the official input/output shape
  -> neeshops/agent.py       coordinates one conversation turn
  -> conversation/           remembers and interprets the shopper
  -> retrieval/              finds possible products
  -> ranking/                orders the possible products
  -> starter/agent.py        removes internal-only fields
  -> Evaluator               scores the returned parent_asin values
```

The research code does not sit inside each response. It runs different safe
configurations through the evaluator and records which configuration scored
better. The frontend is a separate demo view and must never be imported by
the official Agent.

## Words you will see often

| Term | Plain meaning |
|---|---|
| Agent | The Python class the evaluator talks to |
| Session | One shopper conversation, identified by `session_id` |
| Turn | One shopper message followed by one Agent response |
| Constraint | A stated need such as black, leather, size 8, or under $100 |
| Buying | The shopper already has specific requirements |
| Browsing | The shopper is exploring and needs more guidance |
| Intent Override | A newer preference replaces an older preference |
| Boundary | The shopper says they have no preference for an attribute |
| BM25 | Keyword search that rewards products containing useful query words |
| Semantic retrieval | Search by meaning using numeric text embeddings |
| Candidate | A possible product returned by retrieval |
| Reranking | Reordering candidates using more context or a smarter model |
| Personalisation | A small ranking signal derived from the safe user profile |
| Fallback | A simpler path used when an optional model is unavailable |
| Hit Rate@10 | How often the target appears anywhere in the returned Top 10 |
| MRR | How high the target ranks; rank 1 is best |
| MTTC | How many turns it takes to find the target; lower is better |

## Five beginner-safe work areas

Each person should own one area. Start by reading the named module README,
then run only that area's tests before editing anything.

| Person | Owns | First test command | First coding task |
|---|---|---|---|
| P1 Conversation | `neeshops/conversation/` | `pytest -q tests/test_state.py tests/test_intent_override.py` | Extend constraint extraction and its tests |
| P2 Retrieval | `neeshops/retrieval/` | `pytest -q tests/test_retrieval.py` | Validate BM25, then implement semantic retrieval |
| P3 Ranking | `neeshops/ranking/`, `personalization/` | `pytest -q tests/test_ranking.py` | Add a safe LLM-reranker integration with fallback |
| P4 Research | `neeshops/research/`, evaluation scripts | `pytest -q tests/test_research.py` | Reproduce and record comparable baselines |
| P5 Integration | adapters, config, integration tests, demo | `pytest -q tests/test_agent_contract.py tests/test_agent_smoke.py` | Fix/guard the full turn order and contract checks |

Detailed acceptance steps are in `WORKSTREAM_QUICKSTARTS.md`. The shared
two-day order is in `TWO_DAY_FULL_SCOPE_PLAN.md`.

## Rules that protect the whole team

1. Never edit `evaluator/` to improve a score.
2. Never commit `.env`, API keys, downloaded catalog files, generated indexes,
   or evaluator outputs.
3. Never change `starter.Agent.reset()` or `starter.Agent.respond()` without
   P5 reviewing the official schema.
4. Use explicit current requests as hard information. User-profile data is
   only a soft ranking hint.
5. A new explicit value replaces the old value for the same field.
6. `NO_PREFERENCE` means never ask that field again in the session.
7. An optional LLM or embedding failure must fall back to the deterministic
   path and still return a valid response.
8. Measure changes with the same dataset and baseline configuration.
9. Run your focused tests while working and the full `pytest -q` before a
   merge.
10. Update the relevant module README when behavior or an interface changes.

## A safe beginner workflow

Check the current branch before creating your own:

```bash
git branch --show-current
git status --short
git switch -c feature/<your-area>
```

Then repeat this small cycle:

1. Choose one acceptance check from `WORKSTREAM_QUICKSTARTS.md`.
2. Write or update a test showing the expected behavior.
3. Make the smallest code change that passes it.
4. Run the focused tests.
5. Run `pytest -q`.
6. Commit with a message describing the behavior, not just the filename.
7. Tell P5 if you changed a shared function signature or response shape.

Do not leave five large branches until the last hour. Use the integration
checkpoints in the two-day plan.

## What “finished” means

The full-scope project is finished only when all of these are true:

- official catalog validated at 50,000 products;
- official response contract tested on non-empty recommendations;
- Buying, Browsing, Intent Override, and Boundary flows tested end to end;
- conversation constraints affect retrieval on the same turn;
- BM25 and semantic retrieval both work and merge reproducibly;
- metadata filters cover every inferable field documented by the team;
- heuristic ranking always works;
- LLM reranking works when enabled and falls back safely when unavailable;
- personalisation remains a soft signal;
- a baseline and candidate use the same dataset and are both recorded;
- scenario-aware experiments produce reproducible accept/reject records;
- full evaluator, holdout check, and full tests pass;
- token usage, latency, cost, limitations, and team contributions are written;
- one real multi-turn Agent trace and demo are ready.

## If you are stuck

Use this four-line help format in the team chat:

```text
Goal: what acceptance check I am implementing
Command: the exact command I ran
Result: the complete error or unexpected output
Tried: one or two things I already checked
```

Do not silently redesign an interface to work around a problem. Check
`INTEGRATION_CONTRACTS.md`, then ask the provider and consumer of that
interface together.

## Read next

1. `TWO_DAY_FULL_SCOPE_PLAN.md`
2. `WORKSTREAM_QUICKSTARTS.md` — only your own section first
3. `TRACK4_REQUIREMENTS.md`
4. your module's README
5. `INTEGRATION_CONTRACTS.md` before touching a shared boundary

Use `PROJECT_OVERVIEW.md`, `ARCHITECTURE.md`, `FOLDER_GUIDE.md`, and the full
`TEAM_WORKSTREAMS.md` as reference documents rather than trying to memorize
them before starting.
