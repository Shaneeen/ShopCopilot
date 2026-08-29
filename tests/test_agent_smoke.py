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

