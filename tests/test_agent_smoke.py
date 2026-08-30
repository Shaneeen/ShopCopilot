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
