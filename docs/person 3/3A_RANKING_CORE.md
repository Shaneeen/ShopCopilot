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
