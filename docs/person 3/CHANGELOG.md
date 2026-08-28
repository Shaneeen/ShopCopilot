# Person 3 Changelog

Running log of changes made under the Person 3A / 3B split. Tag each entry
`[3A]` (Ranking Core) or `[3B]` (Personalisation & Evaluation). Newest
entries at the top.

## 2026-08-29

- `[3A]` Implemented the guarded `LLMReranker` foundation: config-bounded
  candidate input, truncated product payloads, strict known-ID validation,
  usage/latency evidence, and deterministic `HeuristicRanker` fallback. Added
  focused tests for success, malformed output, duplicate/unknown IDs, provider
  failure, and disabled mode.
- `[3A]` Standardized `person_3a_ranking_handoff.json` schema version 1.0,
  including exact field types, baseline/ranked top-10 semantics, validation
  rules, and the message sent to 3B.
- `[3A]` Added the repeatable P2 candidate-input → 3A top-10 ranking → 3B
  evaluation-handoff workflow, including validation gates, run-record schema,
  tests, and a copy/paste handoff checklist.
- `[setup]` Split the original Person 3 workstream
  (`docs/neeshops/TEAM_WORKSTREAMS.md`) into 3A (Ranking Core,
  `neeshops/ranking/`) and 3B (Personalisation & Evaluation,
  `neeshops/personalization/`) so two people can work on it concurrently.
  Added `docs/person 3/README.md`, `3A_RANKING_CORE.md`,
  `3B_PERSONALIZATION_EVAL.md`, and `HOW_A_AND_B_WORK_TOGETHER.md` on
  branch `Shaneen`.
