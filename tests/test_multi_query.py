"""Multi-query retrieval plumbing: per-angle query building, override-turn
slot handling, and question counting from history."""
from neeshops.agent import NeeShopsAgent
from neeshops.conversation.clarification import ClarificationEngine
from neeshops.conversation.constraints import extract_constraints
from neeshops.models.session import ConversationState, Turn


def test_conversation_query_accumulates_through_override():
    """Override turns keep the accumulation: the user's actual target never
    changes, so earlier keywords stay true — only slot-filling is skipped."""
    state = ConversationState(session_id="s")
    state.history.append(Turn(turn=1, user_message="blue cotton dress"))
    query = NeeShopsAgent._conversation_query(
        state, "Actually, ignore my earlier preference. What I need is: silk scarf."
    )
    assert "cotton" in query and "silk" in query and "scarf" in query


def test_override_message_is_not_slot_filled():
    """The override message must not be parsed as the answer to the question
    asked on the previous turn."""
    updates = extract_constraints(
        "Actually, ignore my earlier preference. What I need is: color: blue.",
        slot="other",
    )
    assert updates.get("color") == "blue"
    assert "feature" not in updates
    assert "other" not in updates


def test_build_retrieval_queries_has_three_angles():
    agent = NeeShopsAgent()
    state = ConversationState(
        session_id="s", constraints={"category": "women shirts", "color": "black"}
    )
    queries = agent.build_retrieval_queries(state, "under $30 maybe")
    assert set(queries) == {"accumulated", "latest", "constraints"}
    assert "shirts" in queries["constraints"] and "black" in queries["constraints"]
    assert "30" in queries["latest"]


def test_questions_counted_from_history_not_deduped_attributes():
    """asked_attributes is deduplicated, so repeating one attribute must
    still exhaust the question budget via history counting."""
    engine = ClarificationEngine(strategy={"clarification": {
        "strategy": "adaptive",
        "max_questions_per_session": 2,
        "other_max_asks": 5,
        "min_candidates_before_recommend": 5,
        "ask_if_candidates_above": 60,
    }}, catalog_lookup={})
    state = ConversationState(session_id="s")
    for turn in (1, 2):
        state.history.append(
            Turn(turn=turn, user_message="ans", asked_attribute="other", informative=True)
        )
        state.asked_attributes.append("other")  # dedupes to one entry
    decision = engine.decide(state, [], turn=3)
    assert decision["ask_attribute"] is None
