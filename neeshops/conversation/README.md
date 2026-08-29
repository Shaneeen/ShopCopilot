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

## **Current implementation**

- `state.py`: in-memory dict of `ConversationState` keyed by `session_id`.
  `apply_turn` **overrides** constraint values field-by-field (never
  appends) — a new explicit value replaces the previous value. `NO_PREFERENCE`
  is stored as a constraint value and is never asked again by the
  clarification engine.

- `intent.py`: sticky heuristic scoring Buying vs. Browsing keyword
  signals + presence of a price + constraint count.

- `constraints.py`: keyword/regex extraction for all declared constraint
  fields:
  `category`, `material`, `color`, `size`, `style`, `brand`, `budget`,
  `feature`, and `use_case`. Also supports richer budget wording and
  no-preference phrases. Extracted values are returned as override-ready
  `{field: value}` updates.

- `clarification.py`: asks when the candidate pool is too broad or too
  thin while there is still question budget remaining. It skips fields
  that have already been answered, previously asked, or marked
  `NO_PREFERENCE`. Once the question budget is exhausted, it recommends
  from available candidates rather than asking additional questions.

- `tests/`: covers constraint extraction, Buying/Browsing routing, intent
  overrides, state persistence, clarification boundaries, no-preference
  handling, repeated-question prevention, and question-budget behaviour.

## How to extend

Add more extraction patterns to `extract_constraints()` — it already
returns override-ready `{field: value}` updates, and `StateManager`
already applies them correctly. Don't touch `apply_turn`'s override
semantics without re-running `tests/test_intent_override.py`.

## **How to test**

Run the full test suite:

```bash
python3 -m pytest -q \
tests/test_state.py \
tests/test_constraints.py \
tests/test_intent.py \
tests/test_intent_override.py \
tests/test_clarification.py \
tests/test_agent_smoke.py
```


### 3. Replace `Known TODOs`

```markdown
## **Known TODOs**

- Verify with the Integration workstream that updated conversation state is
  applied **before retrieval on the same turn**, so newly extracted
  constraints and overrides affect retrieval immediately.

- Evaluate `detect_route` against the official 40/40/15/5 scenario mix once
  simulator sessions are available.

- Inspect failed Boundary/Override evaluator sessions when available and
  refine edge-case state transitions or wording based on observed failures.