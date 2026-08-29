"""One complete simulated Agent interaction must not crash, catalog or not."""
from starter.agent import Agent


def test_multi_turn_conversation_does_not_crash():
    agent = Agent()
    session_id = "smoke-1"
    agent.reset(session_id, user_profile={"preference_tags": ["durability"]})

    turns = [
        "I need a gift for my girlfriend, something casual",
        "Under $120 please",
        "She prefers sneakers over dressier shoes",
    ]
    for turn_idx, message in enumerate(turns, start=1):
        result = agent.respond(session_id, message, turn=turn_idx, top_k=10)
        assert "message" in result
        assert "recommendations" in result


def test_agent_handles_multiple_concurrent_sessions():
    agent = Agent()
    agent.reset("a", user_profile={})
    agent.reset("b", user_profile={})

    result_a = agent.respond("a", "blue jacket", turn=1, top_k=10)
    result_b = agent.respond("b", "red boots", turn=1, top_k=10)

    assert result_a is not None
    assert result_b is not None


def test_turn_sequence_updates_state_before_retrieval_and_filters():
    from neeshops.agent import NeeShopsAgent
    from neeshops.models.session import ConversationState
    from neeshops.retrieval.base import Candidate, Retriever

    captured_states: list[ConversationState] = []

    class SpyRetriever(Retriever):
        name = "spy"

        def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
            # Capture a snapshot of state when search is invoked
            captured_states.append(
                ConversationState(
                    session_id=state.session_id,
                    turn=state.turn,
                    route=state.route,
                    constraints=dict(state.constraints),
                )
            )
            return [Candidate(parent_asin="B001", score=1.0, source="spy")]

    agent = NeeShopsAgent(retriever=SpyRetriever())
    agent.reset("seq_test", user_profile={})
    agent.respond("seq_test", "I want black shoes under $50", turn=1, top_k=10)

    assert len(captured_states) == 1
    state_at_search = captured_states[0]
    # StateManager.apply_turn + extract_constraints + detect_route must have happened BEFORE search
    assert state_at_search.turn == 1
    assert state_at_search.route in ("buying", "browsing")
    assert state_at_search.constraints.get("color") == "black"
    assert state_at_search.constraints.get("budget") == 50.0


def test_config_driven_ranker_fallback_on_unavailable_or_failing_ranker():
    from typing import Any
    from neeshops.agent import NeeShopsAgent
    from neeshops.ranking.base import Ranker
    from neeshops.retrieval.base import Candidate, Retriever

    class DummyRetriever(Retriever):
        name = "dummy"

        def search(self, query: str, state: Any, top_k: int) -> list[Candidate]:
            return [Candidate(parent_asin=f"B00{i}", score=1.0, source="dummy") for i in range(1, 7)]

    class FailingRanker(Ranker):
        name = "failing"

        def rank(self, candidates, catalog_lookup, state, top_k):
            raise NotImplementedError("LLM reranker unavailable")

    agent = NeeShopsAgent(retriever=DummyRetriever(), ranker=FailingRanker())
    agent.reset("fallback_test", user_profile={})
    result = agent.respond("fallback_test", "shoes", turn=1, top_k=10)

    # Response succeeds via fallback to HeuristicRanker
    assert result["recommendations"]
    assert result["recommendations"][0]["parent_asin"] == "B001"


def test_buying_scenario_archetype_e2e():
    """Buying archetype (P5-D4): High-intent, explicit constraints, Buying route."""
    agent = Agent()
    session_id = "buying_e2e"
    agent.reset(session_id, user_profile={"preference_tags": ["shoes"]})

    # Turn 1: Explicit buying intent with color and budget
    r1 = agent.respond(session_id, "I want to buy black running shoes under $100", turn=1, top_k=10)
    assert isinstance(r1["message"], str) and r1["message"]
    assert isinstance(r1["recommendations"], list)
    assert len(r1["recommendations"]) <= 10
    assert "usage" in r1

    # Verify underlying state
    state1 = agent._impl.state_manager.get(session_id)
    assert state1.route == "buying"
    assert state1.constraints.get("color") == "black"
    assert state1.constraints.get("budget") == 100.0

    # Turn 2: Follow-up refinement
    r2 = agent.respond(session_id, "Looking for comfortable athletic sneakers", turn=2, top_k=10)
    assert isinstance(r2["message"], str)
    assert len(r2["recommendations"]) <= 10
    state2 = agent._impl.state_manager.get(session_id)
    assert state2.route == "buying"
    assert state2.constraints.get("color") == "black"


def test_browsing_scenario_archetype_e2e():
    """Browsing archetype (P5-D4): Open-ended, exploratory intent, Browsing route."""
    agent = Agent()
    session_id = "browsing_e2e"
    agent.reset(session_id, user_profile={})

    # Turn 1: Open-ended discovery query
    r1 = agent.respond(session_id, "I'm looking for some inspiration and ideas for casual weekend outfits", turn=1, top_k=10)
    assert isinstance(r1["message"], str) and r1["message"]
    assert isinstance(r1["recommendations"], list)
    assert len(r1["recommendations"]) <= 10

    state1 = agent._impl.state_manager.get(session_id)
    assert state1.route == "browsing"

    # Turn 2: Continued exploratory conversation
    r2 = agent.respond(session_id, "Something comfortable for outdoor walks and warm weather", turn=2, top_k=10)
    assert isinstance(r2["message"], str)
    assert len(r2["recommendations"]) <= 10


def test_intent_override_scenario_archetype_e2e():
    """Intent Override archetype (P5-D4): Explicit slot override replaces old value without merging."""
    agent = Agent()
    session_id = "override_e2e"
    agent.reset(session_id, user_profile={})

    # Turn 1: Initial constraint (blue)
    r1 = agent.respond(session_id, "I need blue running shoes under $90", turn=1, top_k=10)
    state1 = agent._impl.state_manager.get(session_id)
    assert state1.constraints.get("color") == "blue"
    assert state1.constraints.get("budget") == 90.0

    # Turn 2: Intent override (forget blue, switch to red)
    r2 = agent.respond(session_id, "Actually, forget blue, I want red shoes instead", turn=2, top_k=10)
    state2 = agent._impl.state_manager.get(session_id)
    assert state2.constraints.get("color") == "red"
    assert state2.constraints.get("color") != "blue"
    assert state2.constraints.get("color") != "blue + red"
    assert state2.constraints.get("budget") == 90.0
    assert isinstance(r2["recommendations"], list)

    # Turn 3: Budget override
    r3 = agent.respond(session_id, "Make that under $60 please", turn=3, top_k=10)
    state3 = agent._impl.state_manager.get(session_id)
    assert state3.constraints.get("budget") == 60.0
    assert state3.constraints.get("color") == "red"


def test_boundary_scenario_archetype_e2e():
    """Boundary archetype (P5-D4): Explicit NO_PREFERENCE is recorded and never re-asked."""
    from neeshops.models.session import NO_PREFERENCE

    agent = Agent()
    session_id = "boundary_e2e"
    agent.reset(session_id, user_profile={})

    # Turn 1: Broad start
    r1 = agent.respond(session_id, "I'm looking for a winter jacket", turn=1, top_k=10)
    assert isinstance(r1["message"], str)

    # Turn 2: Explicit no-preference on color
    r2 = agent.respond(session_id, "I have no preference on color", turn=2, top_k=10)
    state2 = agent._impl.state_manager.get(session_id)
    assert state2.constraints.get("color") == NO_PREFERENCE
    assert state2.has_no_preference("color")

    # Turn 3: Follow-up turn — clarification must never ask for color
    r3 = agent.respond(session_id, "Under $150 please", turn=3, top_k=10)
    assert r3.get("ask_attribute") != "color"
    state3 = agent._impl.state_manager.get(session_id)
    assert state3.has_no_preference("color")
    assert state3.constraints.get("budget") == 150.0


