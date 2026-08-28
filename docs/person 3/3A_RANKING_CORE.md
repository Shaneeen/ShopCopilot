# Person 3A — Ranking Core

Half of the original **Person 3** workstream. See [README.md](./README.md)
for how this relates to 3B, and
[HOW_A_AND_B_WORK_TOGETHER.md](./HOW_A_AND_B_WORK_TOGETHER.md) for
concurrency rules.

## Owned folders

`neeshops/ranking/` (plus the ranker-selection lines in `neeshops/agent.py`
— see "Shared file" note below).

## Allowed/shared interfaces

Provides: `Ranker` (ABC), `HeuristicRanker`, `LLMReranker` (see
`docs/neeshops/INTEGRATION_CONTRACTS.md` → "Retrieval ↔ Ranking").
Consumes: `list[Candidate]` from P2 (retrieval), `personalization_boost`
from 3B.

## Files to avoid modifying

`neeshops/retrieval/`, `neeshops/conversation/`, `neeshops/personalization/`
(3B's folder), `evaluator/`.

## Responsibilities

- Candidate reranking (`HeuristicRanker` — already done).
- LLM reranking (`LLMReranker`) — bounded candidate count in, token usage
  tracked, secrets from environment variables only, working fallback when
  unavailable.
- Wiring ranker selection into `neeshops/agent.py` so it is config-driven
  instead of hardcoding `HeuristicRanker`.
- Ranking explanation strings, ranking latency/token cost.

## Deliverables

- **P3-D1** — Deterministic baseline reranker exists.
  *Acceptance*: `HeuristicRanker` — **already done and tested**
  (`tests/test_ranking.py`).
- **P3-D3** — If an LLM reranker is used: bounded candidate count in,
  token usage tracked, secrets from environment variables only, and a
  working fallback when unavailable.
  *Acceptance*: `LLMReranker` currently raises `NotImplementedError` when
  disabled — implement it AND wire the fallback into `neeshops/agent.py`
  (currently always constructs `HeuristicRanker` unconditionally; this is
  the actual integration gap).
- **P3-D4** — Ranker output is a valid, ordered `parent_asin` list.
  *Acceptance*: **already done** for `HeuristicRanker`.

## Success metrics

MRR, Top-10 ordering quality, latency, token usage/cost if an LLM is used
— all measured, never estimated.

## Merge checklist

- [ ] `pytest tests/test_ranking.py tests/test_agent_smoke.py` passes
- [ ] No numeric confidence fabricated in `reason` strings
- [ ] LLM path (if implemented) has a tested fallback
- [ ] Ranker selection in `neeshops/agent.py` merged with 3B's edits
      (see shared-file note below) without silently dropping either change

## Definition of Done

`LLMReranker` functional and gated correctly, `neeshops/agent.py` chooses
between rankers based on availability rather than hardcoding
`HeuristicRanker`, `neeshops/ranking/README.md` updated.

## First action

Wire a config-driven ranker choice into `neeshops/agent.py`.

## Shared file: `neeshops/agent.py`

3A owns the *ranker-selection* logic in this file. 3B may also touch this
file to wire in `personalization_boost` output. Neither owns the whole
file — see [HOW_A_AND_B_WORK_TOGETHER.md](./HOW_A_AND_B_WORK_TOGETHER.md)
for how to avoid collisions.
