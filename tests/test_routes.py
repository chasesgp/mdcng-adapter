from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main


def test_health() -> None:
    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_chat_completions_adds_stream_false_and_cleans_json(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_forward_request(*, request, body, force_json, settings):
        captured["body"] = json.loads(body)
        captured["force_json"] = force_json
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "id": "chatcmpl-upstream",
                "object": "chat.completion",
                "created": 1782426849,
                "model": "grok-test",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi"}}],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 2,
                    "total_tokens": 3,
                    "prompt_tokens_details": {"cached_tokens": 1},
                },
            },
        )

    monkeypatch.setattr(main, "_forward_request", fake_forward_request)

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-testabcd"},
            json={"model": "grok-test", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert captured["force_json"] is True
    assert captured["body"]["stream"] is False
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["usage"] == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


def test_chat_completions_forwards_builtin_prompt_replacement_when_stream_exists(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_forward_request(*, request, body, force_json, settings):
        captured["body"] = json.loads(body)
        captured["force_json"] = force_json
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi"}}]},
        )

    monkeypatch.setattr(main, "_forward_request", fake_forward_request)

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "grok-test",
                "stream": False,
                "messages": [
                    {"role": "system", "content": "system prompt 以 mdcng-adapter清洗为准"},
                    {"role": "user", "content": "最強顔面レベル楪カレンが見つめてくれる天国射精"},
                ],
                "temperature": 0.8,
                "max_tokens": 2048,
            },
        )

    assert response.status_code == 200
    assert captured["force_json"] is True
    forwarded_body = captured["body"]
    assert forwarded_body["stream"] is False
    assert forwarded_body["temperature"] == 0.2
    assert forwarded_body["max_tokens"] == 128
    assert "当前字段：标题" in forwarded_body["messages"][0]["content"]
    assert forwarded_body["messages"][1]["content"] == "最強顔面レベル楪カレンが見つめてくれる天国射精"


def test_chat_completions_aggregates_sse(monkeypatch) -> None:
    async def fake_forward_request(*, request, body, force_json, settings):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b'data: {"choices":[{"delta":{"role":"assistant","content":"Hi"}}]}\n'
                b'data: {"choices":[{"delta":{"content":"!"}}]}\n'
                b"data: [DONE]\n"
            ),
        )

    monkeypatch.setattr(main, "_forward_request", fake_forward_request)

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "grok-test", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["choices"][0]["message"]["content"] == "Hi!"


def test_non_grok_chat_response_passthrough_and_preserves_body(monkeypatch) -> None:
    original_body = b'{"model":"gpt-5.4-mini", "messages":[]}'
    captured: dict[str, object] = {}

    async def fake_forward_request(*, request, body, force_json, settings):
        captured["body"] = body
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "x-upstream": "yes"},
            content=b'{"vendor_extra":true}',
        )

    monkeypatch.setattr(main, "_forward_request", fake_forward_request)

    with TestClient(main.app) as client:
        response = client.post("/v1/chat/completions", content=original_body, headers={"Content-Type": "application/json"})

    assert response.status_code == 200
    assert captured["body"] == original_body
    assert response.headers["x-upstream"] == "yes"
    assert response.content == b'{"vendor_extra":true}'


def test_invalid_chat_json_returns_400() -> None:
    with TestClient(main.app) as client:
        response = client.post("/v1/chat/completions", content=b"not-json")

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_chat_completions_returns_502_when_upstream_response_too_large(monkeypatch) -> None:
    async def fake_forward_request(*, request, body, force_json, settings):
        raise main.UpstreamResponseTooLargeError

    monkeypatch.setattr(main, "_forward_request", fake_forward_request)

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "grok-test", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_response_too_large"


def test_read_limited_response_allows_response_within_limit() -> None:
    response = httpx.Response(200, content=b"abc")

    content = asyncio.run(main._read_limited_response(response, 3))

    assert content == b"abc"


def test_read_limited_response_rejects_response_over_limit() -> None:
    response = httpx.Response(200, content=b"abcd")

    with pytest.raises(main.UpstreamResponseTooLargeError):
        asyncio.run(main._read_limited_response(response, 3))


def test_other_paths_are_passthrough(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_forward_request(*, request, body, force_json, settings):
        captured["path"] = request.url.path
        captured["body"] = body
        captured["force_json"] = force_json
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b'{"data":[]}')

    monkeypatch.setattr(main, "_forward_request", fake_forward_request)

    with TestClient(main.app) as client:
        response = client.get("/v1/models?limit=1")

    assert response.status_code == 200
    assert response.json() == {"data": []}
    assert captured == {"path": "/v1/models", "body": b"", "force_json": False}


def test_truncate_prompt_returns_preview_and_truncation_flag() -> None:
    assert main._truncate_prompt("short", 10) == ("short", False)
    assert main._truncate_prompt("abcdef", 3) == ("abc...", True)


def test_body_preview_serializes_escapes_and_truncates() -> None:
    preview, truncated, body_bytes = main._body_preview({"message": "line1\nline2", "value": 1}, 19)

    assert preview == '{"message":"line1\\n...'
    assert truncated is True
    assert body_bytes == len('{"message":"line1\\nline2","value":1}'.encode("utf-8"))


def test_body_debug_log_includes_request_and_response_preview(caplog) -> None:
    caplog.set_level(logging.INFO, logger="mdcng_adapter")

    main._log_body_preview(
        body_debug_type="response",
        body_stage="upstream_response",
        body=b'{"choices":[{"message":{"content":"Hi"}}]}',
        max_chars=200,
        model="grok-test",
        status=200,
        content_type="application/json",
    )

    log_text = "\n".join(caplog.messages)
    assert "body_debug=true" in log_text
    assert "body_debug_type=response" in log_text
    assert "body_stage=upstream_response" in log_text
    assert "model=grok-test" in log_text
    assert "upstream_status=200" in log_text
    assert "content_type=application/json" in log_text
    assert "body_preview={\"choices\":[{\"message\":{\"content\":\"Hi\"}}]}" in log_text
    assert "body_truncated=false" in log_text


def test_chat_completions_logs_enabled_request_and_response_bodies(monkeypatch) -> None:
    async def fake_forward_request(*, request, body, force_json, settings):
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"choices": [{"message": {"role": "assistant", "content": "Hi"}}]},
        )

    body_log_calls: list[dict[str, object]] = []

    def fake_log_body_preview(**kwargs):
        body_log_calls.append(kwargs)

    monkeypatch.setenv("DEBUG_LOG_REQUEST_BODY", "true")
    monkeypatch.setenv("DEBUG_LOG_RESPONSE_BODY", "true")
    monkeypatch.setattr(main, "_forward_request", fake_forward_request)
    monkeypatch.setattr(main, "_log_body_preview", fake_log_body_preview)

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "grok-test", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert [call["body_stage"] for call in body_log_calls] == ["upstream_request", "upstream_response", "adapter_response"]
    assert body_log_calls[0]["body_debug_type"] == "request"
    assert body_log_calls[1]["body_debug_type"] == "response"
    assert body_log_calls[2]["body_debug_type"] == "response"


def test_prompt_debug_log_includes_previews_and_escapes_newlines(monkeypatch, caplog) -> None:
    del monkeypatch
    caplog.set_level(logging.INFO, logger="mdcng_adapter")

    main._log_prompt_preview(
        {
            "model": "grok-test",
            "temperature": 0.2,
            "max_tokens": 2048,
            "stream": False,
            "messages": [
                {"role": "system", "content": "第一行\n第二行"},
                {"role": "user", "content": "Translate\tthis"},
                {"role": "user", "content": [{"type": "text", "text": "hidden"}]},
            ],
        },
        100,
    )

    log_text = "\n".join(caplog.messages)
    assert "prompt_debug=true" in log_text
    assert "model=grok-test" in log_text
    assert "messages_count=3" in log_text
    assert "system_prompt_count=1" in log_text
    assert "user_prompt_count=2" in log_text
    assert "system_prompt_preview=第一行\\n第二行" in log_text
    assert "user_prompt_preview=Translate\\tthis\\n---\\n<non-string content: list>" in log_text
    assert "temperature=0.2" in log_text
    assert "max_tokens=2048" in log_text
    assert "stream=false" in log_text
    assert "prompt_truncated=false" in log_text
    assert "authorization" not in log_text.lower()


def test_prompt_debug_log_marks_missing_system_and_truncation(monkeypatch, caplog) -> None:
    del monkeypatch
    caplog.set_level(logging.INFO, logger="mdcng_adapter")

    main._log_prompt_preview(
        {"model": "grok-test", "messages": [{"role": "user", "content": "Translate this title"}]},
        5,
    )

    log_text = "\n".join(caplog.messages)
    assert "prompt_debug=true" in log_text
    assert "system_prompt_count=0" in log_text
    assert "system_prompt_preview=-" in log_text
    assert "user_prompt_preview=Trans..." in log_text
    assert "prompt_truncated=true" in log_text


def test_prompt_debug_log_is_disabled_by_default(monkeypatch, caplog) -> None:
    async def fake_forward_request(*, request, body, force_json, settings):
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"choices": []})

    prompt_log_calls: list[tuple[dict[str, object], int]] = []

    monkeypatch.delenv("DEBUG_LOG_PROMPT", raising=False)
    monkeypatch.setattr(main, "_forward_request", fake_forward_request)
    monkeypatch.setattr(main, "_log_prompt_preview", lambda body, max_chars: prompt_log_calls.append((body, max_chars)))
    caplog.set_level(logging.INFO, logger="mdcng_adapter")

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "grok-test", "messages": [{"role": "user", "content": "hidden prompt"}]},
        )

    assert response.status_code == 200
    assert prompt_log_calls == []
    log_text = "\n".join(caplog.messages)
    assert "prompt_debug=true" not in log_text
    assert "system_prompt_preview" not in log_text
    assert "user_prompt_preview" not in log_text
