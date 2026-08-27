# `neeshops/ranking/`

**Owner/workstream**: Person 3 — Ranking, Query Intelligence &
Personalisation (see `docs/neeshops/TEAM_WORKSTREAMS.md`, which also owns
`neeshops/personalization/`).

## Purpose

Order retrieval candidates and attach a human-readable reason. This is
where MRR gets won or lost — retrieval finding the right product is
necessary but not sufficient; it needs to land near rank 1.

## Public interfaces

```python
class Ranker(ABC):
    name: str
    def rank(self, candidates: list[Candidate], catalog_lookup: dict,
              state: ConversationState, top_k: int) -> list[Recommendation]: ...
```

`Recommendation`: `parent_asin`, `score` (internal ordering score — never
presented as a fabricated confidence), `reason` (human-readable), `source`.

Implementations: `HeuristicRanker` (working, used by `neeshops/agent.py`
unconditionally today), `LLMReranker` (stub).

## Current implementation

`HeuristicRanker`: reranks the top `ranking.rerank_limit` candidates
(config), blends each candidate's retrieval score with
`neeshops.personalization.profile.personalization_boost()` weighted by
`ranking.personalization_weight` (default 0.15 — deliberately small, so an
explicit request always dominates a soft profile signal — Track 4
requirement 7), and assigns one of three fixed human-readable reasons by
rank position.

## How to extend

`LLMReranker.rank()` currently raises `NotImplementedError`. To implement
it: bound the candidate count sent to the LLM, track `usage` tokens (the
official contract's `usage.prompt_tokens`/`completion_tokens` — see
`neeshops/agent.py`'s response shape), read credentials only from
`neeshops.config.settings.get_settings()` (never hardcode a key), and
**never let it be the only ranker** — `neeshops/agent.py` should fall back
to `HeuristicRanker` when `LLMReranker.is_available()` is false or a call
fails. That fallback wiring doesn't exist yet — it's the actual
integration task, not just the LLM call itself.

## How to test

```bash
pytest tests/test_ranking.py tests/test_agent_smoke.py
```

## Known TODOs

- `LLMReranker` unimplemented (primary P3 deliverable).
- No fallback wiring in `neeshops/agent.py` yet between rankers.
- Ranking has never been measured against the real catalog/evaluator in
  this environment.
