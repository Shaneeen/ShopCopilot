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

Implementations: `RetrievalOrderRanker` (R0), preserved `HeuristicRanker`
(R1), `ConstraintAwareRanker` (R2), `FusionAwareRanker` (R3), and
`LLMReranker` (R5 experiment with Gemini and offline fake provider). R4
CrossEncoder and R6 Hybrid remain planned.

## Current implementation

`HeuristicRanker`: reranks the top `ranking.rerank_limit` candidates
(config), blends each candidate's retrieval score with
`neeshops.personalization.profile.personalization_boost()` weighted by
`ranking.personalization_weight` (default 0.15 — deliberately small, so an
explicit request always dominates a soft profile signal — Track 4
requirement 7), and assigns one of three fixed human-readable reasons by
rank position.

R2/R3 extract deterministic `RankingFeatures` separately from aggregation.
They prioritize the count of explicit hard-constraint mismatches, then a
configuration-weighted relevance score, then original retrieval rank. Missing
catalog metadata is unknown, not a mismatch. Internal diagnostics expose
feature values, constraint statuses, and final relevance without changing the
public recommendation contract.

All R2/R3 weights and ablation switches are in `ranking.deterministic`.
Normalization supports raw, min-max, and rank signals. RRF is implemented for
genuine independent source rankings, but current P2 candidates contain only a
merged score and source label, so real P2 RRF evaluation is pending.

`RankingExperimentHarness` can register any ranker and records synthetic flag,
configuration, retrieval/ranked top tens, measured latency, fallback/error,
and target rank when a target is defined. A newer strategy is not assumed to
be better; use the same case and pool for comparison.

## Optional semantic reranking

`LLMReranker` accepts a narrow `RankingProvider`:

```python
provider.rerank(request, timeout_seconds) -> ProviderResult(
    ordered_ids=["B001", "B002"],
    prompt_tokens=12,
    completion_tokens=4,
)
```

It first obtains deterministic heuristic order, then sends at most
`ranking.llm.rerank_limit` candidates (30 by default) only when at least two
explicit shopper constraints are meaningful. It truncates catalog text,
accepts only known unique IDs, fills omissions in heuristic order, and falls
back safely on every provider failure. Per-call evidence is available as
`last_usage`, `last_latency_ms`, and `last_fallback_reason`.

`GeminiRankingProvider` uses `google-genai`, `GEMINI_API_KEY`, Pydantic
structured output, and the configured real HTTP timeout. `FakeRankingProvider`
requires no credential, network, or SDK call. LLM reranking is disabled by
default, so ordinary operation and tests remain offline.

## How to test

```bash
pytest tests/test_ranking.py tests/test_agent_smoke.py
pytest -q tests/test_deterministic_ranking.py tests/test_ranking_experiments.py
pytest -q tests/test_llm_reranker.py tests/test_gemini_provider.py
```

## Known TODOs

- No fallback wiring in `neeshops/agent.py` yet between rankers (coordinate
  with P5 in Phase 4).
- Ranking has never been measured against the real catalog/evaluator in
  this environment.
- P2 does not expose independent BM25/semantic ranks, so live RRF cannot yet
  be reconstructed from `Candidate`.
