from __future__ import annotations

import json
from typing import Any, Iterable

from .sanitizer import build_chat_completion_response


def is_sse_content_type(content_type: str) -> bool:
    return "text/event-stream" in content_type.lower()


def iter_sse_data(raw: bytes | str) -> Iterable[str]:
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    data_lines: list[str] = []

    for line in text.splitlines():
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            payload = line[5:].lstrip(" ")
            if data_lines and _is_complete_payload("\n".join(data_lines)):
                yield "\n".join(data_lines)
                data_lines = []
            data_lines.append(payload)

    if data_lines:
        yield "\n".join(data_lines)


def aggregate_sse_to_chat_completion(
    raw: bytes | str,
    request_model: str | None = None,
    *,
    max_events: int | None = None,
    max_content_chars: int | None = None,
) -> dict[str, Any]:
    content_parts: dict[int, list[str]] = {}
    roles_by_index: dict[int, str] = {}
    finish_reasons_by_index: dict[int, str] = {}
    response_id: str | None = None
    created: int | None = None
    model = request_model
    usage: object | None = None
    event_count = 0
    content_chars = 0

    for payload in iter_sse_data(raw):
        event_count += 1
        if max_events is not None and event_count > max_events:
            raise ValueError("too many SSE events")

        payload = payload.strip()
        if not payload:
            continue
        if payload == "[DONE]":
            break

        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid SSE data JSON") from exc

        if not isinstance(chunk, dict):
            continue

        response_id = response_id or _as_str(chunk.get("id"))
        created = created or _as_int(chunk.get("created"))
        model = model or _as_str(chunk.get("model"))
        usage = usage or chunk.get("usage")
        content_chars += _merge_choices(chunk.get("choices"), content_parts, roles_by_index, finish_reasons_by_index)
        if max_content_chars is not None and content_chars > max_content_chars:
            raise ValueError("SSE content too large")

    contents_by_index = {index: "".join(parts) for index, parts in content_parts.items()} or {0: ""}
    return build_chat_completion_response(
        model=model,
        contents_by_index=contents_by_index,
        roles_by_index=roles_by_index,
        finish_reasons_by_index=finish_reasons_by_index,
        response_id=response_id,
        created=created,
        usage=usage,
    )


def _merge_choices(
    choices: object,
    content_parts: dict[int, list[str]],
    roles_by_index: dict[int, str],
    finish_reasons_by_index: dict[int, str],
) -> int:
    added_content_chars = 0
    if not isinstance(choices, list):
        return added_content_chars

    for fallback_index, choice in enumerate(choices):
        if not isinstance(choice, dict):
            continue
        index = _as_int(choice.get("index"), fallback_index)
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}

        role = _as_str(delta.get("role")) or _as_str(message.get("role"))
        if role:
            roles_by_index[index] = role

        content = delta.get("content") if "content" in delta else message.get("content")
        if content is not None:
            text = _content_to_text(content)
            content_parts.setdefault(index, []).append(text)
            added_content_chars += len(text)

        finish_reason = _as_str(choice.get("finish_reason"))
        if finish_reason:
            finish_reasons_by_index[index] = finish_reason

    return added_content_chars


def _is_complete_payload(payload: str) -> bool:
    stripped = payload.strip()
    if not stripped:
        return False
    if stripped == "[DONE]":
        return True
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _content_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_int(value: object, default: int | None = None) -> int | None:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default
