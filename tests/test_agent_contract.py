"""starter.agent.Agent must expose exactly the shape the official evaluator
imports and calls."""
from starter.agent import Agent


def test_agent_exposes_required_methods():
    agent = Agent()
    assert hasattr(agent, "reset")
    assert hasattr(agent, "respond")


def test_respond_returns_expected_keys():
    agent = Agent()
    agent.reset("s1", user_profile={})
    result = agent.respond("s1", "I need black running shoes under $80", turn=1, top_k=10)

    assert isinstance(result, dict)
    assert "message" in result
    assert "recommendations" in result
    assert isinstance(result["message"], str)
    assert isinstance(result["recommendations"], list)


def test_respond_recommendation_shape():
    agent = Agent()
    agent.reset("s2", user_profile={})
    result = agent.respond("s2", "black running shoes", turn=1, top_k=5)
    for rec in result["recommendations"]:
        assert "parent_asin" in rec
        assert "reason" in rec
