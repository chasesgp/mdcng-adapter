from __future__ import annotations

from app.config import Settings
from app.sanitizer import sanitize_chat_completion_response, sanitize_chat_request


def test_grok_request_adds_stream_false_when_missing() -> None:
    body = {"model": "grok-4.20-0309-non-reasoning-console", "messages": []}

    sanitized, stream_modified, target_model = sanitize_chat_request(body, Settings())

    assert target_model is True
    assert stream_modified is True
    assert sanitized["stream"] is False
    assert "stream" not in body


def test_grok_request_does_not_override_existing_stream() -> None:
    body = {"model": "grok-4.20-0309-non-reasoning-console", "messages": [], "stream": True}

    sanitized, stream_modified, target_model = sanitize_chat_request(body, Settings())

    assert target_model is True
    assert stream_modified is False
    assert sanitized["stream"] is True


def test_non_grok_request_is_not_modified() -> None:
    body = {"model": "gpt-5.4-mini", "messages": []}

    sanitized, stream_modified, target_model = sanitize_chat_request(body, Settings())

    assert target_model is False
    assert stream_modified is False
    assert sanitized is body


def test_response_sanitizer_removes_usage_detail_fields() -> None:
    payload = {
        "id": "chatcmpl-1",
        "object": "chat.completion.extra",
        "created": 1782426849,
        "model": "grok-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hi"},
                "finish_reason": "stop",
                "extra": "ignored",
            }
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
            "prompt_tokens_details": {"cached_tokens": 1},
            "completion_tokens_details": {"reasoning_tokens": 1},
        },
        "vendor_extra": "ignored",
    }

    sanitized = sanitize_chat_completion_response(payload)

    assert sanitized == {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1782426849,
        "model": "grok-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
