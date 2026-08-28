"""The LLM ranker is bounded, validates IDs, and always fails soft."""
from neeshops.models.session import ConversationState
from neeshops.ranking.llm_reranker import LLMReranker
from neeshops.retrieval.base import Candidate


def _strategy(limit: int = 40) -> dict:
    return {"ranking": {"rerank_limit": limit, "personalization_weight": 0.15}}


def _candidates(count: int = 4) -> list[Candidate]:
    return [Candidate(f"B{i:03}", float(count - i), "bm25+semantic") for i in range(count)]


def test_valid_llm_order_is_used_and_usage_is_recorded():
    def client(payload, timeout):
        assert timeout == 5.0
        return {
            "ordered_ids": ["B002", "B000", "B001"],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }

    ranker = LLMReranker(client=client, strategy=_strategy())
    recs = ranker.rank(_candidates(), {}, ConversationState(session_id="s"), 3)

    assert [rec.parent_asin for rec in recs] == ["B002", "B000", "B001"]
    assert ranker.last_usage == {"prompt_tokens": 12, "completion_tokens": 4}
    assert ranker.last_fallback_reason is None


def test_payload_is_bounded_by_config_and_product_text_is_truncated():
    observed = {}

    def client(payload, timeout):
        observed.update(payload)
        return {"ordered_ids": ["B000"]}

    lookup = {"B000": {"title": "x" * 500, "features": ["y" * 500] * 5}}
    ranker = LLMReranker(client=client, strategy=_strategy(limit=2))
    ranker.rank(_candidates(5), lookup, ConversationState(session_id="s"), 10)

    assert len(observed["products"]) == 2
    assert len(observed["products"][0]["title"]) == 200
    assert len(observed["products"][0]["features"]) == 3
    assert len(observed["products"][0]["features"][0]) == 160


def test_unknown_and_duplicate_ids_are_removed_then_baseline_fills_result():
    def client(payload, timeout):
        return {"ordered_ids": ["UNKNOWN", "B002", "B002"]}

    ranker = LLMReranker(client=client, strategy=_strategy())
    recs = ranker.rank(_candidates(), {}, ConversationState(session_id="s"), 3)

    assert [rec.parent_asin for rec in recs] == ["B002", "B000", "B001"]


def test_malformed_response_falls_back_without_raising():
    ranker = LLMReranker(
        client=lambda payload, timeout: {"not_ordered_ids": []},
        strategy=_strategy(),
    )
    recs = ranker.rank(_candidates(), {}, ConversationState(session_id="s"), 2)

    assert [rec.parent_asin for rec in recs] == ["B000", "B001"]
    assert ranker.last_fallback_reason == "LLM returned no valid candidate IDs"
    assert ranker.last_usage == {"prompt_tokens": 0, "completion_tokens": 0}


def test_provider_failure_falls_back_without_raising():
    def failing_client(payload, timeout):
        raise TimeoutError("provider timed out")

    ranker = LLMReranker(client=failing_client, strategy=_strategy())
    recs = ranker.rank(_candidates(), {}, ConversationState(session_id="s"), 2)

    assert [rec.parent_asin for rec in recs] == ["B000", "B001"]
    assert ranker.last_fallback_reason == "LLM call failed: TimeoutError"


def test_disabled_without_client_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.setenv("NEESHOPS_ENABLE_LLM_RERANKER", "false")
    from neeshops.config.settings import get_settings

    get_settings.cache_clear()
    try:
        ranker = LLMReranker(strategy=_strategy())
        recs = ranker.rank(_candidates(), {}, ConversationState(session_id="s"), 2)
    finally:
        get_settings.cache_clear()

    assert [rec.parent_asin for rec in recs] == ["B000", "B001"]
    assert ranker.last_fallback_reason
