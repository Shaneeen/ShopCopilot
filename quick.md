# Person 3 Combined — Quick Team Update

**Branch:** `shaneen-Person3_combined`  
**Current checkpoint:** `2bf7ca7`  
**Tests:** 101 passed, 1 optional Gemini test deselected

## Where Person 3 is now

Person 3's ranking and personalisation work is combined and working offline.
The current flow is:

```text
P1 current ConversationState
        ↓
P2 retrieval Candidates
        ↓
Person 3 deterministic ranking
        ↓
Person 3 soft personalisation
        ↓
optional Gemini reranking (off by default)
        ↓
ordered top recommendations
```

The CrossEncoder stage is planned next but has **not** been implemented yet.

## What is completed

### Ranking

- **R0 — Retrieval order:** returns candidates in P2's original order.
- **R1 — Existing heuristic:** preserved as the original baseline.
- **R2 — Constraint-aware ranking:** checks current category, color, material,
  size, brand, and budget requirements before using softer relevance signals.
- **R3 — Fusion-aware infrastructure:** supports raw, min-max, rank
  normalization, and tested Reciprocal Rank Fusion (RRF).
- Missing product metadata is treated as **unknown**, not automatically wrong.
- Current intent overrides old intent; ranking does not reuse stale constraints.
- Internal diagnostics show why a product moved without changing the official
  Agent response format.

### Personalisation

- `personalization_boost(product_row, user_profile) -> float` is implemented.
- Personalisation is a soft signal and cannot override an explicit current
  requirement.
- Weight-sweep and retrieval-vs-ranking evaluation scripts are available.
- Existing evaluation results are under `evaluation/results/`.

### Optional Gemini reranking

- Gemini support uses the official `google-genai` SDK.
- It is disabled by default, so normal development requires no key or network.
- It has bounded input, structured output, timeout handling, ID validation,
  token/latency tracking, and deterministic fallback.
- A fake offline provider is available for tests.

### Experiment support

`RankingExperimentHarness` can run the same state and candidate pool through
R0, R1, R2, and R3. It records the configuration, original and resulting top
10, latency, fallback/error, and target rank when a target is known. Future
R4/R5/R6 rankers can be registered without rebuilding the harness.

## What teammates can use now

### Person 1 — Conversation State

Person 3 consumes the current `ConversationState.constraints` dictionary and
does not mutate it. Your existing override behavior is exactly what ranking
needs:

```text
Earlier: color = black
Current: color = brown
Ranking uses only brown.
```

Useful contract:

```python
state.constraints
state.user_profile
```

No P1 schema change is currently requested. Please keep budget numeric where
possible and continue replacing old values rather than appending them.

### Person 2 — Retrieval

Person 3 accepts the existing contract:

```python
Candidate(parent_asin: str, score: float, source: str)
```

Please provide a reasonably sized candidate pool, not only the final top 10,
plus matching catalog rows. Current source labels such as `bm25`, `semantic`,
and `bm25+semantic` are supported.

Important limitation: the current `Candidate` contains one merged score. Real
RRF comparison needs the independent BM25 and semantic ranks. If these can be
included in a separate experiment artifact later, Person 3 can evaluate true
RRF without changing the public `Candidate` contract immediately.

### Person 4 — Research and Evaluation

You can use:

- `neeshops/ranking/experiments.py` for same-input R0/R1/R2/R3 comparisons;
- `scripts/evaluate_ranking_ab.py` for retrieval-order vs ranked comparison;
- `scripts/evaluate_personalization_weights.py` for personalisation sweeps;
- `evaluation/results/` for current structured and human-readable outputs.

Please compare strategies on identical cases and candidate pools. A newer
ranker is not assumed to be better until MRR, HitRate@10, latency, and relevant
scenario results are measured.

### Person 5 — Agent Integration

The stable public ranking call remains:

```python
ranker.rank(candidates, catalog_lookup, state, top_k)
```

It returns ordered `Recommendation` objects containing `parent_asin`, `score`,
`reason`, and `source`. Internal feature diagnostics must not be added to the
official Agent response.

The current Agent still constructs `HeuristicRanker` directly. Later we need
to coordinate a small config-driven selection seam so P5 can choose the agreed
ranker and preserve deterministic fallback. Gemini must remain optional and
off by default.

## What Person 3 will work on next

1. Add **R4 — local CrossEncoder reranking** over a bounded R2/R3 shortlist.
2. Keep R0/R1/R2/R3 available so R4 can be compared fairly.
3. Avoid model downloads during normal offline tests and provide a safe local
   fallback if the CrossEncoder is unavailable.
4. Validate ranking against real P2 candidate pools when they are ready.
5. Re-run ranking and personalisation comparisons with Person 4.
6. Coordinate final ranker selection and usage/latency wiring with Person 5.

## Quick verification

```bash
pytest -q
```

Expected current result:

```text
101 passed, 1 deselected
```

More detail is available in:

- `docs/person 3/3A_RANKING_CORE.md`
- `docs/person 3/3B_PERSONALIZATION_EVAL.md`
- `docs/person 3/HOW_A_AND_B_WORK_TOGETHER.md`
- `docs/person 3/CHANGELOG.md`
