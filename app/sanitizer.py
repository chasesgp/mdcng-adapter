from __future__ import annotations

import time
import uuid
from typing import Any

from .config import Settings


def is_target_model(model: object, prefixes: tuple[str, ...]) -> bool:
    if not isinstance(model, str):
        return False
    normalized = model.lower()
    return any(normalized.startswith(prefix) for prefix in prefixes)


def sanitize_chat_request(body: dict[str, Any], settings: Settings) -> tuple[dict[str, Any], bool, bool]:
    model = body.get("model")
    target_model = is_target_model(model, settings.grok_model_prefixes)
    stream_modified = False

    if target_model and settings.force_stream_false and "stream" not in body:
        body = dict(body)
        body["stream"] = False
        stream_modified = True

    return body, stream_modified, target_model


def standard_usage(usage: object | None = None) -> dict[str, int]:
    if not isinstance(usage, dict):
        usage = {}
    prompt_tokens = _to_int(usage.get("prompt_tokens"))
    completion_tokens = _to_int(usage.get("completion_tokens"))
    total_tokens = _to_int(usage.get("total_tokens"), prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def sanitize_chat_completion_response(data: dict[str, Any], request_model: str | None = None) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        choices = [
            {
                "index": 0,
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "stop",
            }
        ]

    return {
        "id": _string_or_default(data.get("id"), _adapter_id()),
        "object": "chat.completion",
        "created": _to_int(data.get("created"), int(time.time())),
        "model": _string_or_default(data.get("model"), request_model or ""),
        "choices": [_sanitize_choice(choice, index) for index, choice in enumerate(choices)],
        "usage": standard_usage(data.get("usage")),
    }


def build_chat_completion_response(
    *,
    model: str | None,
    contents_by_index: dict[int, str] | None = None,
    roles_by_index: dict[int, str] | None = None,
    finish_reasons_by_index: dict[int, str] | None = None,
    response_id: str | None = None,
    created: int | None = None,
    usage: object | None = None,
) -> dict[str, Any]:
    contents_by_index = contents_by_index or {0: ""}
    roles_by_index = roles_by_index or {}
    finish_reasons_by_index = finish_reasons_by_index or {}
    choices = []

    for choice_index in sorted(contents_by_index):
        choices.append(
            {
                "index": choice_index,
                "message": {
                    "role": roles_by_index.get(choice_index, "assistant"),
                    "content": contents_by_index.get(choice_index, ""),
                },
                "finish_reason": finish_reasons_by_index.get(choice_index, "stop"),
            }
        )

    if not choices:
        choices.append(
            {
                "index": 0,
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "stop",
            }
        )

    return {
        "id": response_id or _adapter_id(),
        "object": "chat.completion",
        "created": created or int(time.time()),
        "model": model or "",
        "choices": choices,
        "usage": standard_usage(usage),
    }


def _sanitize_choice(choice: object, fallback_index: int) -> dict[str, Any]:
    if not isinstance(choice, dict):
        choice = {}

    message = choice.get("message")
    if not isinstance(message, dict):
        message = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}

    return {
        "index": _to_int(choice.get("index"), fallback_index),
        "message": {
            "role": _string_or_default(message.get("role"), "assistant"),
            "content": _content_to_text(message.get("content")),
        },
        "finish_reason": _string_or_default(choice.get("finish_reason"), "stop"),
    }


def _content_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _to_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _adapter_id() -> str:
    return f"chatcmpl-adapter-{uuid.uuid4().hex}"
