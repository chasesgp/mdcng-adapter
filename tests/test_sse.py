from __future__ import annotations

import pytest

from app.sse import aggregate_sse_to_chat_completion, is_sse_content_type, iter_sse_data


def test_sse_content_type_detection() -> None:
    assert is_sse_content_type("text/event-stream; charset=utf-8") is True
    assert is_sse_content_type("application/json") is False


def test_iter_sse_data_handles_consecutive_data_lines() -> None:
    raw = """
data: {"a":1}
data: {"b":2}
data: [DONE]
""".strip()

    assert list(iter_sse_data(raw)) == ['{"a":1}', '{"b":2}', '[DONE]']


def test_aggregate_sse_to_chat_completion() -> None:
    raw = """
data: {"id":"chatcmpl-upstream","created":1782426849,"model":"grok-upstream","choices":[{"index":0,"delta":{"role":"assistant","content":"Hi"}}]}
data: {"choices":[{"index":0,"delta":{"content":"!"},"finish_reason":"stop"}]}
data: [DONE]
""".strip()

    payload = aggregate_sse_to_chat_completion(raw, request_model="grok-request")

    assert payload["id"] == "chatcmpl-upstream"
    assert payload["object"] == "chat.completion"
    assert payload["created"] == 1782426849
    assert payload["model"] == "grok-request"
    assert payload["choices"] == [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hi!"},
            "finish_reason": "stop",
        }
    ]
    assert payload["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_aggregate_sse_supports_multiline_data_event() -> None:
    raw = """
data: {"choices":
data: [{"index":0,"delta":{"role":"assistant","content":"Hi"}}]}
data: {"choices":[{"index":0,"delta":{"content":"!"}}]}
data: [DONE]
""".strip()

    payload = aggregate_sse_to_chat_completion(raw, request_model="grok-test")

    assert payload["choices"][0]["message"] == {"role": "assistant", "content": "Hi!"}


def test_aggregate_sse_enforces_event_limit() -> None:
    with pytest.raises(ValueError, match="too many SSE events"):
        aggregate_sse_to_chat_completion(
            "data: {\"choices\":[]}\ndata: {\"choices\":[]}\n",
            max_events=1,
        )


def test_aggregate_sse_enforces_content_limit() -> None:
    with pytest.raises(ValueError, match="SSE content too large"):
        aggregate_sse_to_chat_completion(
            'data: {"choices":[{"delta":{"content":"abcdef"}}]}',
            max_content_chars=3,
        )


def test_aggregate_sse_raises_for_invalid_json_data() -> None:
    with pytest.raises(ValueError):
        aggregate_sse_to_chat_completion("data: not-json\ndata: [DONE]")
