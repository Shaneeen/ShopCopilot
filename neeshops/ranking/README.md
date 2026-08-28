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
unconditionally today), `LLMReranker` (guarded ranking core implemented;
provider adapter and P5-owned agent wiring remain).

## Current implementation

`HeuristicRanker`: reranks the top `ranking.rerank_limit` candidates
(config), blends each candidate's retrieval score with
`neeshops.personalization.profile.personalization_boost()` weighted by
`ranking.personalization_weight` (default 0.15 — deliberately small, so an
explicit request always dominates a soft profile signal — Track 4
requirement 7), and assigns one of three fixed human-readable reasons by
rank position.

## LLM reranking base

`LLMReranker` accepts an injected provider adapter with this contract:

```python
def client(payload: dict, timeout_seconds: float) -> dict:
    return {
        "ordered_ids": ["B001", "B002"],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
    }
```

It sends at most `ranking.rerank_limit` candidates (40 by default), truncates
catalog text, accepts only known unique IDs, fills omitted IDs using the
deterministic heuristic order, and falls back to `HeuristicRanker` on disabled,
malformed, timeout, or provider-error paths. Per-call evidence is available as
`last_usage`, `last_latency_ms`, and `last_fallback_reason`.

The next integration step is a provider-specific adapter using credentials from
`get_settings()` and P5-owned wiring in `neeshops/agent.py`. Do not put provider
SDK imports or secrets in the ranking policy itself.

## How to test

```bash
pytest tests/test_ranking.py tests/test_agent_smoke.py
pytest -q tests/test_llm_reranker.py
```

## Known TODOs

- No provider adapter or fallback wiring in `neeshops/agent.py` yet between
  rankers (coordinate with P5).
- Ranking has never been measured against the real catalog/evaluator in
  this environment.
