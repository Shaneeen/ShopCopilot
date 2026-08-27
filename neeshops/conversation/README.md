# `neeshops/conversation/`

**Owner/workstream**: Person 1 — Conversation Intelligence & State (see
`docs/neeshops/TEAM_WORKSTREAMS.md`).

## Purpose

Turn one turn's free text plus prior state into: updated structured
constraints (intent-override semantics), a Buying/Browsing route, and a
clarification decision (ask something / recommend / both).

## Public interfaces

```python
StateManager.reset(session_id, user_profile) -> ConversationState
StateManager.get(session_id) -> ConversationState
StateManager.apply_turn(session_id, turn, user_message,
                         extracted_constraints, route,
                         asked_attribute=None) -> ConversationState
StateManager.record_recommendations(session_id, asins) -> None
StateManager.mark_no_preference(session_id, field) -> None

extract_constraints(message, known_fields=None) -> dict
detect_route(message, previous_route, constraint_count) -> str  # "buying" | "browsing"

ClarificationEngine.decide(state, candidates, turn) -> {
    "ask_attribute": str | None,
    "question": str | None,
    "should_recommend": bool,
}
```

Called only by `neeshops/agent.py`.

## Current implementation

- `state.py`: in-memory dict of `ConversationState` keyed by `session_id`.
  `apply_turn` **overrides** constraint values field-by-field (never
  appends) — this is the Intent Override mechanism (Track 4 requirement
  4). `NO_PREFERENCE` is just a stored constraint value — the
  clarification engine skips any field already set (see `is_unset`).
- `intent.py`: sticky heuristic scoring buying vs. browsing keyword
  signals + presence of a price + constraint count.
- `constraints.py`: keyword/regex extraction. **Only `color`, `budget`,
  and no-preference phrases are populated today** — `material`, `size`,
  `style`, `brand`, `feature`, `use_case` are declared but not yet
  extracted from text.
- `clarification.py`: asks when the candidate pool is too broad or too
  thin (below `clarification.min_candidates_before_recommend` and there's
  still question budget left), otherwise recommends from whatever exists
  once the budget (`clarification.max_questions_per_session`) runs out —
  this avoids a dead-end turn with neither a question nor a
  recommendation.

## How to extend

Add more extraction patterns to `extract_constraints()` — it already
returns override-ready `{field: value}` updates, and `StateManager`
already applies them correctly. Don't touch `apply_turn`'s override
semantics without re-running `tests/test_intent_override.py`.

## How to test

```bash
pytest tests/test_state.py tests/test_intent_override.py tests/test_agent_smoke.py tests/test_agent_contract.py
```

## Known TODOs

- Populate `material`/`size`/`style`/`brand`/`feature`/`use_case`
  extraction (highest leverage for Hit Rate@10 on Buying scenarios).
- `detect_route` has never been measured against the official 40/40/15/5
  scenario mix — only unit-tested in isolation.
