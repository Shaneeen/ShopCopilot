# How 3A and 3B Work at the Same Time

The split only helps if 3A and 3B can actually work in parallel without
blocking each other. Rules below make that concrete.

## 1. Folder ownership is the primary boundary

- 3A writes only in `neeshops/ranking/`.
- 3B writes only in `neeshops/personalization/`.
- Neither touches `neeshops/retrieval/`, `neeshops/conversation/`,
  `starter/agent.py`, or `evaluator/` (both inherit this restriction from
  the original Person 3 scope).

Because these are disjoint folders, 3A and 3B can branch, edit, test, and
commit independently with **no merge conflicts** in the normal case.

## 2. The interface between them is a pure function call

3B's `personalization_boost()` is consumed by 3A's ranker as a function
call, not by editing each other's internals:

```
ranking_score = base_score + ranking.personalization_weight * personalization_boost(candidate, user_profile)
```

As long as `personalization_boost(candidate, user_profile) -> float` keeps
its existing signature (see `docs/neeshops/INTEGRATION_CONTRACTS.md` →
"Profile ↔ Ranking"), 3A can build/test `HeuristicRanker` and
`LLMReranker` against a stub or the real function without waiting on 3B's
changes to land, and 3B can change the internals of
`personalization_boost` freely without touching `neeshops/ranking/`.

**Rule**: if either person needs to change the function signature, they
post in the team channel *before* changing it, not after — a signature
change is the one thing that can break the other side silently.

## 3. The one shared file: `neeshops/agent.py`

Both sub-roles have a reason to touch this file:

- 3A: switching ranker construction from hardcoded `HeuristicRanker` to a
  config-driven choice (with `LLMReranker` fallback).
- 3B: wiring `personalization_boost` output into the pipeline, if not
  already wired.

To avoid stepping on each other:

1. Each person edits **only their own lines** — keep the ranker-selection
   block and the personalization-wiring block visually separate (own
   functions or clearly commented sections) so diffs don't overlap.
2. Commit and push/pull small, frequent changes to this file rather than
   holding a long-lived local diff.
3. If a conflict does happen, it will be a small, mechanical merge (two
   non-overlapping blocks in the same file) — resolve by keeping both
   blocks, not by picking one side.

## 4. Testing stays independent

- 3A runs `pytest tests/test_ranking.py tests/test_agent_smoke.py` against
  `neeshops/ranking/` changes.
- 3B runs the same test command against `neeshops/personalization/`
  changes plus the P3-D5 comparison script.
- Both must pass before either merges — but neither needs the other's
  branch merged first to run their own tests, since
  `personalization_boost` and `HeuristicRanker`/`LLMReranker` are each
  independently testable against the documented interface.

## 5. Sequencing note for P3-D5

3B's P3-D5 MRR comparison uses whatever ranker 3A currently has merged.
If 3B finishes the comparison script before 3A merges `LLMReranker`, that
is fine — report the delta against `HeuristicRanker` first, then re-run
once `LLMReranker` lands. Don't block P3-D5 on `LLMReranker` being done.

## 6. Log every change

Every commit that lands under this split gets one line in
[CHANGELOG.md](./CHANGELOG.md), tagged `[3A]` or `[3B]`, so it stays clear
who changed what and when even though both are nominally "Person 3."
