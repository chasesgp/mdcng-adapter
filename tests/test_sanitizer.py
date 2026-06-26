from __future__ import annotations

from app.config import Settings
from app.sanitizer import (
    BUILTIN_PROMPT_FIELD_OVERVIEW,
    BUILTIN_PROMPT_FIELD_TITLE,
    infer_mdcng_field_type,
    sanitize_chat_completion_response,
    sanitize_chat_request,
)


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


def test_infer_mdcng_field_type_detects_title_and_overview() -> None:
    assert infer_mdcng_field_type("最強顔面レベル楪カレンが見つめてくれる天国射精") == BUILTIN_PROMPT_FIELD_TITLE
    assert infer_mdcng_field_type("第一段<br>第二段") == BUILTIN_PROMPT_FIELD_OVERVIEW
    assert infer_mdcng_field_type("第一句。第二句！") == BUILTIN_PROMPT_FIELD_OVERVIEW


def test_builtin_prompt_trigger_replaces_system_prompt_and_optimizes_title_request() -> None:
    trigger = "system prompt 以 mdcng-adapter清洗为准"
    body = {
        "model": "grok-test",
        "stream": False,
        "messages": [
            {"role": "system", "content": f" {trigger} "},
            {"role": "user", "content": "最強顔面レベル楪カレンが見つめてくれる天国射精"},
        ],
        "temperature": 0.8,
        "max_tokens": 2048,
        "tools": [
            {"type": "web_search"},
            {"type": "function", "function": {"name": "keep_tool"}},
        ],
        "tool_choice": {"type": "web_search"},
        "search_parameters": {"mode": "on"},
        "web_search_options": {"enabled": True},
    }

    sanitized, stream_modified, target_model = sanitize_chat_request(body, Settings())

    assert target_model is True
    assert stream_modified is False
    assert sanitized is not body
    assert sanitized["temperature"] == 0.2
    assert sanitized["max_tokens"] == 128
    assert sanitized["tool_choice"] == "none"
    assert sanitized["tools"] == [{"type": "function", "function": {"name": "keep_tool"}}]
    assert "search_parameters" not in sanitized
    assert "web_search_options" not in sanitized
    assert body["messages"][0]["content"] == f" {trigger} "

    system_prompt = sanitized["messages"][0]["content"]
    assert trigger not in system_prompt
    assert "当前字段：标题" in system_prompt
    assert "不超过30个汉字" in system_prompt
    assert "不要调用工具" in system_prompt


def test_builtin_prompt_trigger_uses_overview_rules_for_html_content() -> None:
    body = {
        "model": "grok-test",
        "stream": False,
        "messages": [
            {"role": "system", "content": "system prompt 以 mdcng-adapter清洗为准"},
            {"role": "user", "content": "第一段<br>第二段。第三段。"},
        ],
    }

    sanitized, stream_modified, target_model = sanitize_chat_request(body, Settings())

    assert target_model is True
    assert stream_modified is False
    assert sanitized["max_tokens"] == 1024
    assert "当前字段：简介" in sanitized["messages"][0]["content"]
    assert "禁止换行" in sanitized["messages"][0]["content"]


def test_builtin_prompt_is_not_applied_without_trigger() -> None:
    body = {
        "model": "grok-test",
        "stream": False,
        "messages": [
            {"role": "system", "content": "普通 system prompt"},
            {"role": "user", "content": "hi"},
        ],
        "temperature": 0.8,
        "max_tokens": 2048,
    }

    sanitized, stream_modified, target_model = sanitize_chat_request(body, Settings())

    assert target_model is True
    assert stream_modified is False
    assert sanitized is body
    assert sanitized["temperature"] == 0.8
    assert sanitized["max_tokens"] == 2048


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
