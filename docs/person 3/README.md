# Person 3 — Split into 3A / 3B

The original **Person 3 — Ranking, Query Intelligence & Personalisation**
workstream (see `docs/neeshops/TEAM_WORKSTREAMS.md`) is split here into two
parallel sub-roles so two people can work on it at the same time without
blocking each other or fighting over the same files.

| Sub-role | Owner scope | Folder |
|---|---|---|
| [Person 3A — Ranking Core](./3A_RANKING_CORE.md) | R0–R3 deterministic experiments, `LLMReranker`, ranker selection in `neeshops/agent.py` | `neeshops/ranking/` |
| [Person 3B — Personalisation & Evaluation](./3B_PERSONALIZATION_EVAL.md) | `personalization_boost`, personalization weighting, P3-D5 MRR comparison experiment | `neeshops/personalization/` |

See [CHANGELOG.md](./CHANGELOG.md) for the running log of changes made
under this split, and [HOW_A_AND_B_WORK_TOGETHER.md](./HOW_A_AND_B_WORK_TOGETHER.md)
for the concurrency rules that let 3A and 3B work at the same time.

## Why split this way

The original deliverables cut cleanly along the two owned folders:

- **3A** owns everything in `neeshops/ranking/` — the `Ranker` ABC,
  retrieval/R1/R2/R3 strategies, experiment harness, and optional
  provider-backed `LLMReranker`
  (P3-D1, P3-D3, P3-D4), plus wiring ranker selection into
  `neeshops/agent.py` (Definition of Done).
- **3B** owns everything in `neeshops/personalization/` — the
  `personalization_boost()` soft-ranking signal (P3-D2), and the
  cross-cutting evaluation deliverable P3-D5 (ranking-strategy vs.
  retrieval-only MRR comparison), which consumes 3A's ranker output but
  doesn't modify `neeshops/ranking/` itself.

This mirrors the "Allowed/shared interfaces" boundary already defined in
`docs/neeshops/TEAM_WORKSTREAMS.md`: `personalization_boost` is a pure
function consumed by the ranker, not a modification of the ranker itself,
so the two folders can be developed independently.
