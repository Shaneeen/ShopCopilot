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
  *Acceptance*: the Gemini and fake providers plus all offline fallback paths
  are complete. Phase 4 still needs the P5-owned `neeshops/agent.py` selection
  seam; it is intentionally outside this phase.
- **P3-D4** — Ranker output is a valid, ordered `parent_asin` list.
  *Acceptance*: **already done** for `HeuristicRanker`.

## Success metrics

MRR, Top-10 ordering quality, latency, token usage/cost if an LLM is used
— all measured, never estimated.

## Roadmap and current position

The Person 3 ranking work is split into six phases, with **Phase 2.5** added
as an engineering-strengthening step. 3A has implemented the original R1,
the R2/R3 experimental deterministic strategies, guarded semantic reranking,
the Gemini adapter, offline fake, and provider tests. Official Agent wiring,
real P2-candidate validation, and measured 3B comparison remain.

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Deterministic ranking baseline | Complete |
| 2 | Safe LLM reranking core | Complete |
| 2.5 | Constraint features, retrieval normalization/fusion, experiment harness | Complete on synthetic fixtures; real P2 comparison pending |
| 3 | Real model-provider adapter | Complete |
| 4 | Official Agent integration with P5 | Not started |
| 5 | P2 candidate integration and ranking-quality evaluation | Ready to start when P2 data is available |
| 6 | 3A handoff to 3B and final measured comparison | Not started |

This status means **the foundation is complete; integration and measured
evaluation remain**. The current official public-set result proves that the
integrated heuristic agent runs, but it does not prove that the new LLM path
improves ranking because that path is not connected to `starter.Agent` yet.

### Phase 1 — Deterministic baseline (complete)

Goal: always produce a valid ordered top 10 without requiring a model or
network connection.

Completed evidence:

- `HeuristicRanker` consumes P2's `Candidate(parent_asin, score, source)`
  objects and returns ordered `Recommendation` objects.
- The configured rerank limit and requested `top_k` are respected.
- Empty catalog lookups and missing product fields degrade gracefully.
- Soft personalisation does not override a much stronger retrieval match.
- Reasons are human-readable and do not claim fabricated confidence.
- The official adapter exposes only contract-safe recommendation fields.

Verify with:

```bash
pytest -vv tests/test_ranking.py tests/test_agent_contract.py
```

### Phase 2.5 — Deterministic ranking engineering (complete on synthetic data)

This phase preserves the original `HeuristicRanker` unchanged and adds an
explicit strategy ladder for apples-to-apples experiments:

| Strategy | Implementation | Status |
|---|---|---|
| R0 Retrieval | `RetrievalOrderRanker` | Implemented; preserves first-seen candidate order |
| R1 Existing Heuristic | `HeuristicRanker` | Preserved baseline; raw merged score plus soft personalization |
| R2 Constraint-Aware | `ConstraintAwareRanker` | Implemented and offline-tested |
| R3 Fusion-Aware | `FusionAwareRanker` | Score normalization implemented; RRF tested synthetically |
| R4 CrossEncoder | — | Planned; deliberately not implemented yet |
| R5 Gemini | `LLMReranker` + Gemini provider | Implemented and experimental |
| R6 Hybrid | — | Planned |

**NEW != BETTER.** Every strategy remains experimental until it is measured
on the same cases and candidate pools. R1 remains selectable as its own class;
the experiment harness registers R0/R1/R2/R3 independently and can later
register R4/R5/R6 without changing its record schema.

#### Feature and constraint model

`RankingFeatureExtractor` is separate from score aggregation. Its internal
`RankingFeatures` record contains normalized retrieval signal and rank;
category, title, feature, color, material, brand, style, size, and budget
signals; hard-violation count; and the existing 3B-owned personalization
boost. `ConstraintEvaluation` retains per-field `MATCH`, `MISMATCH`, or
`UNKNOWN`, hard violations, and soft matches. `last_diagnostics` exposes these
records plus the final relevance score for development only; the public
`Recommendation` and Agent contracts are unchanged.

Current explicit category, color, material, size, brand, and maximum budget
are treated as hard, objectively checkable requirements. Style, feature, and
use case are soft because the current catalog represents them as incomplete
descriptive text. A hard mismatch is recorded only from explicit catalog
metadata (or price). Catalog title/features/details may prove a positive
attribute match, but their silence cannot prove a mismatch. Missing price or
attribute metadata is therefore `UNKNOWN`, never an automatic violation.

R2/R3 order first by hard-violation count, then configured relevance, then
original candidate rank. This ensures soft personalization can move close
candidates but cannot outrank a product that satisfies a current explicit
requirement with one that explicitly violates it. Ranking consumes only the
current `state.constraints`; it never reads history, so P1's override semantics
(for example black replaced by brown) remain authoritative.

All aggregation weights and per-feature ablation switches live under
`ranking.deterministic` in `default_strategy.json`. The current values are
starting hypotheses, not tuned evidence. Features can independently be
disabled for retrieval-only, constraints, metadata-overlap, and personalization
ablations without editing Python.

#### Retrieval normalization and RRF boundary

`normalize_scores` supports `raw`, `minmax`, and rank normalization with
deterministic equal-score, empty, and non-finite handling. R3 defaults to
min-max normalization. `reciprocal_rank_fusion` implements
`sum(1 / (k + rank_in_source))` with configurable `rrf_k=60`, duplicate-ID
protection, and missing-source safety.

P2 currently min-max normalizes BM25 and semantic lists and emits only one
weighted merged `Candidate.score` plus a source label. A label such as
`bm25+semantic` does not contain the independent ranks needed to reconstruct
RRF. Consequently live R3 uses the available merged score normalization.
RRF is active only when genuine per-source rankings are explicitly supplied;
otherwise it safely falls back to rank normalization. Real RRF validation is
pending a P2 contract extension or side-channel artifact containing those
rankings.

#### Experiment harness and verification

`RankingExperimentHarness` runs the same `RankingExperimentCase` through any
registered `Ranker`. Each record contains case and strategy name, configuration,
synthetic flag, input count, original and ranked top tens, measured wall-clock
latency, fallback/error, and optional target rank/reciprocal rank. It does not
invent HitRate or MRR when no target is defined. Synthetic boot fixtures cover
hard material conflict, retrieval conflict, sparse metadata, intent override,
and personalization conflict.

Verify offline with:

```bash
.venv/bin/pytest -vv tests/test_ranking.py tests/test_deterministic_ranking.py tests/test_ranking_experiments.py
```

The recommended R4 next step is a separate local `CrossEncoderRanker` that
consumes the bounded R2/R3 shortlist, preserves deterministic fallback, and is
first evaluated through this harness. No model dependency or download belongs
in Phase 2.5.

### Phase 2 — Safe LLM reranking core (complete)

Goal: enforce the ranking and failure-safety rules before connecting a paid or
external model.

Completed evidence:

- Input is bounded by `ranking.llm.rerank_limit` (30 by default) after the
  deterministic heuristic stage.
- Product titles and features are truncated before building the payload.
- Only known, unique candidate IDs are accepted from model output.
- Omitted IDs are filled deterministically using heuristic order.
- Disabled, malformed, timeout, and provider-error paths fall back to
  `HeuristicRanker` instead of raising or returning an empty result.
- Per-call `last_usage`, `last_latency_ms`, and `last_fallback_reason` are
  available for integration and reporting.

Verify with:

```bash
pytest -vv tests/test_llm_reranker.py
```

### Phase 3 — Google Gemini semantic provider (complete)

Goal: connect the guarded core to the selected provider without changing the
public `Ranker.rank(...)` contract.

Google Gemini is the initial provider, implemented with Google's current
`google-genai` SDK. The default model is the stable Flash-class
`gemini-3.7-flash`; `NEESHOPS_LLM_MODEL` makes this an operational default,
not an architectural dependency. LLM reranking remains off by default.

The production flow is:

```text
P2 candidates
  -> HeuristicRanker deterministic order (up to its configured limit)
  -> top 30 semantic shortlist
  -> optional Gemini ordered IDs
  -> strict known/unique-ID validation and heuristic fill
  -> requested top_k (normally 10)
```

`RankingProvider.rerank(ProviderRequest, timeout_seconds) -> ProviderResult`
is the narrow provider boundary. `GeminiRankingProvider` contains all SDK
details. `FakeRankingProvider` implements the identical interface without an
API key, network, or SDK call and lets tests prescribe an ordering.

#### Eligibility and defaults

Gemini runs only when all of these deterministic conditions hold:

- `NEESHOPS_ENABLE_LLM_RERANKER=true` (or explicit test injection);
- a provider is configured and available;
- at least two meaningful fields from the actual `CONSTRAINT_FIELDS` schema
  are set (`NO_PREFERENCE`, empty, and unknown fields do not count); and
- at least two heuristic candidates are available.

Defaults are `provider=gemini`, `model=gemini-3.7-flash`, semantic
`rerank_limit=30`, `minimum_constraints=2`, and `timeout_seconds=5`. The
heuristic limit remains separately configured at `ranking.rerank_limit=40`.

#### Request and structured response

Gemini receives only current explicit constraints and a deterministic compact
candidate list: `parent_asin`, a title truncated to 200 characters, numeric
price when present, up to five 80-character categories, and up to three
160-character features. It does not receive raw profile data, ratings, store,
retrieval scores, retrieval source, the full catalog object, giant details, or
long descriptions.

The compact instruction defines Gemini as a semantic relevance judge: rank
only supplied IDs, prioritize explicit and hard requirements, invent nothing,
return no scores or explanations, and optionally omit uncertain candidates.
Gemini structured output uses the Pydantic schema:

```json
{"ordered_ids": ["B001", "B004", "B002"]}
```

Every response is still validated locally. Unknown, empty, and duplicate IDs
are removed. Valid partial output is placed first, omitted shortlist IDs retain
heuristic order, and any remaining heuristic candidates follow. Zero valid IDs
causes a complete heuristic fallback.

#### Failure behavior and observability

Disabled, insufficient-constraint, and too-few-candidate skips are intentional,
so they return heuristic results with no fallback error. Actual fallback codes
are `missing_credentials`, `timeout`, `provider_error`,
`malformed_response`, and `invalid_provider_result`. All provider and network
exceptions are sanitized and fail soft; no exception text or key is logged.

The SDK receives the configured timeout through `HttpOptions.timeout` in
milliseconds, which bounds the real HTTP request rather than merely abandoning
a still-running thread. `last_latency_ms` uses `time.perf_counter()` around the
provider call. `last_usage` maps provider-reported input/output counts to
`prompt_tokens` and `completion_tokens`; unavailable metadata stays `None` and
is never fabricated. Cost is not estimated because no pricing configuration
exists yet.

#### Environment and verification

Install and run the offline suite:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -vv tests/test_ranking.py tests/test_llm_reranker.py tests/test_gemini_provider.py
.venv/bin/pytest -q
```

Normal pytest excludes the `integration` marker and requires no credential or
network. Run the optional real smoke test explicitly with:

```bash
.venv/bin/pytest -m integration -s tests/test_gemini_integration.py
```

Supported environment variables (all shown with safe placeholders in
`.env.example`) are:

- `GEMINI_API_KEY`
- `NEESHOPS_ENABLE_LLM_RERANKER`
- `NEESHOPS_LLM_PROVIDER`
- `NEESHOPS_LLM_MODEL`
- `NEESHOPS_LLM_RERANK_LIMIT`
- `NEESHOPS_LLM_MIN_CONSTRAINTS`
- `NEESHOPS_LLM_TIMEOUT_SECONDS`

`.env` and `.env.local` are ignored while `.env.example` remains tracked.
Never put a key in source, fixtures, tests, output, or exceptions.

Current limitations: Gemini needs network when enabled; no model-price table or
estimated cost is maintained; Phase 4 has not exposed usage through the Agent;
and ranking quality has not yet been measured on real P2 candidates.

#### What Shaneen needs to do

1. Go to Google AI Studio and create a Gemini API key.
2. Copy the key.
3. Put it in the local environment as `GEMINI_API_KEY`.
4. Set `NEESHOPS_ENABLE_LLM_RERANKER=true` locally.
5. Run `.venv/bin/pytest -m integration -s tests/test_gemini_integration.py`.

### Phase 4 — Official Agent integration with P5

Goal: make the official entry point choose the configured ranker and expose
real usage without violating `docs/agent_api_contract.json`.

Current blocker: `neeshops/agent.py` still constructs `HeuristicRanker`
unconditionally. P5 owns this seam, so coordinate rather than editing it in
parallel.

Tasks:

- [ ] Choose `LLMReranker` only when enabled and available.
- [ ] Preserve heuristic fallback when a live call fails.
- [ ] Pass measured prompt/completion counts into the official `usage` object.
- [ ] Keep internal `reason` and `source` out of the submitted recommendation
      objects.
- [ ] Continue returning at most ten ordered unique `parent_asin` values.
- [ ] Prove the offline/disabled path still passes the full suite.

Exit checks:

```bash
NEESHOPS_ENABLE_LLM_RERANKER=false pytest -q
pytest -vv tests/test_agent_contract.py tests/test_agent_smoke.py
```

### Phase 5 — P2 integration and ranking-quality evaluation

Goal: prove how 3A changes the order of Person 2's real candidate pool.

Expected flow:

```text
P2 retrieves up to 200 candidates
  -> HeuristicRanker considers the configured top 40
  -> optional Gemini reranks the heuristic top 30
  -> 3A returns the top 10
```

Tasks:

- [ ] Validate P2's real `parent_asin`, numeric `score`, and `source` values.
- [ ] Confirm P2's merged score scale and mixed `bm25+semantic` source label.
- [ ] Check that candidate IDs exist in the frozen catalog.
- [ ] Record retrieval-only, heuristic, and (when enabled) LLM top-10 order.
- [ ] Run repeated inputs to check deterministic fallback behavior.
- [ ] Record measured latency, usage, fallback, config, and Git commit.
- [ ] Generate `person_3a_ranking_handoff.json` using the canonical contract
      below.

Diagnosis rule: if the target is absent from P2's pool, report a retrieval
recall issue to P2. If it is in the pool but outside 3A's top 10, investigate
ranking.

### Phase 6 — 3A handoff to 3B and final comparison

Goal: give 3B stable inputs for an apples-to-apples measured comparison.

Tasks:

- [ ] Hand off retrieval-only, heuristic, and optional LLM top-10 arrays for
      the same evaluator cases.
- [ ] Include case ID, query/state, ranker/config, Git commit, latency, usage,
      and fallback information.
- [ ] Have 3B calculate retrieval, heuristic, and optional LLM MRR plus their
      deltas.
- [ ] Run the official evaluator and report HitRate@10, MRR, MTTC, efficiency,
      technical score, scenario metrics, usage, latency, and cost.
- [ ] Select the final strategy using measured results rather than assuming
      the LLM is better.

The final Person 3 workstream is complete only after 3A's ranking path and
3B's personalisation/evaluation work are both integrated, measured, documented,
and reproducible.

### Recommended execution order from here

1. Optionally run the real Gemini smoke test after a local key is configured.
2. Coordinate the official Agent seam with P5 (Phase 4).
3. Obtain Person 2's real candidate output (Phase 5).
4. Produce a local P2 → heuristic/Gemini top-10 comparison.
5. Generate the first canonical 3A handoff JSON for 3B.
6. Give baseline and ranked results to 3B.
7. Run the official evaluator and select the best measured strategy.
8. Document measured quality, latency, tokens, and any configured cost.

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

## Next Phase 4 action (not part of Phase 3)

Wire a config-driven ranker choice into `neeshops/agent.py`.

## End-to-end working workflow

Use this workflow for every test query. The image from the team discussion
describes the same boundary: Person 2 retrieves a reasonably large mixed-source
candidate pool, then 3A ranks it down to the ten products returned to the user.
The ranking must run through code so that the result is repeatable; do not choose
the final ten manually.

### Step 0 — Agree on the P2 → 3A contract

Before Person 2 hands anything over, agree on:

- the same query text and `ConversationState` (explicit constraints and user
  profile) used for retrieval and ranking;
- a candidate-pool target of about 200 where available (not only the final ten);
- source labels such as `bm25`, `semantic`, or `bm25+semantic`;
- the meaning and scale of `Candidate.score`, especially when sources are
  combined; and
- how semantic and BM25 results are truncated before ranking. If an LLM
  reranker is used, only a bounded slice (normally 20–50 candidates, controlled
  by configuration) should be sent to it and token usage must be recorded.

Person 2's machine-readable handoff is:

```text
query: str
state: ConversationState
candidates: list[Candidate(parent_asin: str, score: float, source: str)]
catalog_lookup: dict[parent_asin, product row]
```

An image or screenshot is useful for discussion, but it is not sufficient as
the implementation handoff. Ask Person 2 for the actual `Candidate` objects (or
equivalent JSON/CSV containing all three fields) so the ranker and tests can
consume them.

### Step 1 — Validate Person 2's input

For each query, check that:

1. the candidate list is ordered as Person 2 intended;
2. every candidate has a non-empty `parent_asin`, numeric `score`, and known
   `source`;
3. duplicate `parent_asin` values have already been merged or are handled
   deterministically;
4. catalog rows are available where possible (a missing row must still degrade
   gracefully); and
5. explicit user constraints have not been lost between retrieval and ranking.

If the candidate pool does not contain the expected product, report that to
Person 2 as a retrieval-recall issue. Ranking cannot promote a product it never
receives.

### Step 2 — Produce the ranked top 10

Call the public interface, keeping the retrieval input unchanged for later
comparison:

```python
ranked = ranker.rank(
    candidates=candidates,
    catalog_lookup=catalog_lookup,
    state=state,
    top_k=10,
)
```

For the baseline, run `HeuristicRanker`. If 3A enables `LLMReranker`, bound its
input, capture latency and actual prompt/completion token counts, and fall back
to `HeuristicRanker` on unavailability or failure. Never hardcode weights outside
`default_strategy.json`.

Verify the result before handing it off:

- zero to ten unique, catalog-valid `parent_asin` values;
- ordered best-first and deterministic for the heuristic path;
- no explicit constraint is overridden by a soft personalisation preference;
- every item has `score`, `source`, and a human-readable `reason`; and
- `reason` does not claim a fabricated numeric confidence.

### Step 3 — Record a reproducible run

Save or report one record per query with this shape. `retrieval_order` is
important: Person B needs it as the no-reranking baseline.

```json
{
  "run_id": "descriptive-unique-id",
  "query": "black sneaker casual",
  "state_summary": {
    "explicit_constraints": {},
    "preference_tags": []
  },
  "ranker": "heuristic",
  "strategy_config": "exact config or commit used",
  "retrieval_order": ["PARENT_ASIN_1", "PARENT_ASIN_2"],
  "ranked_top_10": [
    {
      "parent_asin": "PARENT_ASIN_2",
      "score": 0.0,
      "reason": "Human-readable reason",
      "source": "bm25+semantic"
    }
  ],
  "latency_ms": 0,
  "usage": {"prompt_tokens": 0, "completion_tokens": 0},
  "errors_or_fallback": null,
  "git_commit": "commit SHA"
}
```

The zero values above are placeholders for the schema, not estimated results.
Record measured values from the run. For a non-LLM ranker, token counts may
legitimately be zero.

### Step 4 — Test and commit 3A's work

Run:

```bash
pytest tests/test_ranking.py tests/test_agent_smoke.py
```

Then commit only 3A-owned changes (plus the small, coordinated ranker-selection
block in `neeshops/agent.py`) with a focused message, for example:

```bash
git add neeshops/ranking tests/test_ranking.py
git commit -m "feat(person-3a): rank retrieval candidates into top ten"
```

If `neeshops/agent.py` was changed, stage it explicitly after checking that 3B's
personalisation wiring remains intact.

## 3A → 3B handoff

Person B does not need to wait for every 3A improvement. They can begin against
the existing `HeuristicRanker`, then rerun after an LLM or strategy change lands.
For each evaluation batch, give Person B:

1. the run record above, including both `retrieval_order` and `ranked_top_10`;
2. the query/state or evaluator-case identifier used;
3. the exact ranker name, strategy configuration, and Git commit;
4. measured latency and token usage, plus whether fallback occurred;
5. passing test output; and
6. any known retrieval-recall issues reported back to Person 2.

Person B can then compare the first ten unique IDs in `retrieval_order` (identity
ranker) with `ranked_top_10`, run both through the same evaluator cases, and
report the measured MRR delta. This is the concrete dependency between A and B;
3B should not need to inspect or modify 3A's ranking internals.

### Copy/paste handoff message

```text
3A ranking handoff
- Branch/commit:
- Ranker and config:
- Evaluator cases/run IDs:
- Input candidate count per case:
- Retrieval baseline artifact/location:
- Ranked top-10 artifact/location:
- Tests:
- Measured latency and token usage:
- Fallbacks/errors:
- Known P2 retrieval-recall issues:
- Ready for 3B to run identity-vs-ranked MRR comparison: yes/no
```

## Canonical 3A → 3B JSON contract

The official handoff artifact is one file named
`person_3a_ranking_handoff.json`. Person B can start evaluation using this file
without importing 3A's code or interpreting Person 2's raw candidate format.

Use exactly this structure:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-08-29T12:00:00+08:00",
  "git_commit": "REPLACE_WITH_COMMIT_SHA",
  "ranker": {
    "name": "heuristic",
    "configuration": {
      "personalization_weight": 0.15,
      "rerank_limit": 50
    }
  },
  "runs": [
    {
      "run_id": "case-001",
      "query": "black casual sneakers under $100",
      "state": {
        "explicit_constraints": {
          "category": "sneakers",
          "color": "black",
          "max_price": 100
        },
        "preference_tags": ["casual"]
      },
      "input_candidate_count": 200,
      "retrieval_baseline_top_10": [
        {"rank": 1, "parent_asin": "B000000001"},
        {"rank": 2, "parent_asin": "B000000002"}
      ],
      "ranked_top_10": [
        {
          "rank": 1,
          "parent_asin": "B000000002",
          "score": 0.91,
          "reason": "Best match for your request",
          "source": "bm25+semantic"
        },
        {
          "rank": 2,
          "parent_asin": "B000000001",
          "score": 0.87,
          "reason": "Strong value within your budget",
          "source": "bm25"
        }
      ],
      "metrics": {
        "latency_ms": 14.2,
        "prompt_tokens": 0,
        "completion_tokens": 0
      },
      "fallback": {
        "occurred": false,
        "reason": null
      },
      "error": null
    }
  ]
}
```

The values above are examples only. The delivered file must contain real run
values and real `parent_asin` identifiers.

### Required types and rules

- `schema_version`, `generated_at`, `git_commit`, `run_id`, and `query` are
  strings. `generated_at` uses an ISO 8601 timestamp with timezone.
- `runs` is an array with one object per evaluator query.
- `input_candidate_count` is a non-negative integer.
- `retrieval_baseline_top_10` preserves Person 2's original order before 3A
  ranking. `ranked_top_10` contains 3A's resulting order.
- Both top-10 arrays contain at most ten unique products. `rank` is an integer
  from 1 to 10 and `parent_asin` is a non-empty string.
- Ranked `score` and `metrics.latency_ms` are numbers, not quoted strings.
- `reason` and `source` are strings. Do not put fabricated numeric confidence
  in `reason`.
- Token counts are non-negative integers. They are `0` for
  `HeuristicRanker`; record measured counts for an LLM ranker.
- `fallback.occurred` is boolean. Use JSON `null` for an absent fallback reason
  or error, never the strings `"null"`, `"none"`, or `"N/A"`.
- Do not add, rename, or change field types without coordinating a new
  `schema_version` with 3B.

Person B uses `run_id` to pair the two arrays, evaluates both against the same
expected product, and reports:

```text
baseline_mrr
ranked_mrr
mrr_delta = ranked_mrr - baseline_mrr
```

The full candidate pool is not required for this comparison. Share it only when
3B needs to debug a particular result.

### Message to send with the JSON file

```text
Hi Person B, attached is person_3a_ranking_handoff.json.

The file uses schema version 1.0. Each entry in "runs" represents one
evaluation query.

Use:
- retrieval_baseline_top_10 as the identity/no-reranking result;
- ranked_top_10 as Person A's ranking result;
- run_id to match results belonging to the same evaluator case.

Please evaluate both arrays against the same expected product and report:

baseline_mrr
ranked_mrr
mrr_delta = ranked_mrr - baseline_mrr

You do not need to parse Person 2's raw candidates or call Person A's ranking
code. All IDs required for the comparison are included as parent_asin strings
in the two top-10 arrays.
```

## Shared file: `neeshops/agent.py`

3A owns the *ranker-selection* logic in this file. 3B may also touch this
file to wire in `personalization_boost` output. Neither owns the whole
file — see [HOW_A_AND_B_WORK_TOGETHER.md](./HOW_A_AND_B_WORK_TOGETHER.md)
for how to avoid collisions.
