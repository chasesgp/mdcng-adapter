from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .config import Settings, load_settings
from .errors import (
    adapter_parse_error_response,
    invalid_json_response,
    upstream_error_response,
    upstream_response_too_large_response,
)
from .logging_config import format_log_fields, mask_authorization, setup_logging
from .proxy import build_upstream_headers, build_upstream_url, filter_response_headers
from .sanitizer import sanitize_chat_completion_response, sanitize_chat_request
from .sse import aggregate_sse_to_chat_completion, is_sse_content_type

logger = logging.getLogger("mdcng_adapter")


class UpstreamResponseTooLargeError(Exception):
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    setup_logging(settings.log_level)
    app.state.settings = settings
    app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout), follow_redirects=False)
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(title="MDCNG Grok Adapter", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    started = time.monotonic()
    raw_body = await request.body()
    model = ""
    stream_modified = False
    target_model = False
    response_cleaned = False
    upstream_status: int | None = None
    upstream_content_type = ""
    error_type: str | None = None

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        error_type = "invalid_request_error"
        _log_request(request, started, model, target_model, stream_modified, False, None, "", False, error_type)
        return invalid_json_response()

    if not isinstance(body, dict):
        error_type = "invalid_request_error"
        _log_request(request, started, model, target_model, stream_modified, False, None, "", False, error_type)
        return invalid_json_response()

    model = body.get("model") if isinstance(body.get("model"), str) else ""
    sanitized_body, stream_modified, target_model = sanitize_chat_request(body, settings)
    if settings.debug_log_prompt:
        _log_prompt_preview(sanitized_body, settings.debug_log_prompt_max_chars)
    passthrough = bool(not target_model and settings.passthrough_non_grok and not settings.clean_all_responses)
    upstream_body = (
        json.dumps(sanitized_body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if stream_modified
        else raw_body
    )

    try:
        upstream_response = await _forward_request(
            request=request,
            body=upstream_body,
            force_json=True,
            settings=settings,
        )
    except UpstreamResponseTooLargeError:
        error_type = "upstream_response_too_large"
        _log_request(request, started, model, target_model, stream_modified, passthrough, None, "", False, error_type)
        return upstream_response_too_large_response(settings.max_upstream_response_bytes)
    except httpx.RequestError:
        error_type = "upstream_error"
        _log_request(request, started, model, target_model, stream_modified, passthrough, None, "", False, error_type)
        return upstream_error_response()

    upstream_status = upstream_response.status_code
    upstream_content_type = upstream_response.headers.get("content-type", "")

    if not 200 <= upstream_response.status_code < 300:
        response = _passthrough_response(upstream_response)
        _log_request(request, started, model, target_model, stream_modified, passthrough, upstream_status, upstream_content_type, False, None)
        return response

    should_clean = settings.clean_all_responses or (target_model and settings.clean_grok_response)
    if is_sse_content_type(upstream_content_type) and should_clean:
        try:
            payload = aggregate_sse_to_chat_completion(
                upstream_response.content,
                request_model=model,
                max_events=settings.max_sse_events,
                max_content_chars=settings.max_sse_content_chars,
            )
        except ValueError:
            error_type = "adapter_parse_error"
            _log_request(request, started, model, target_model, stream_modified, passthrough, upstream_status, upstream_content_type, False, error_type)
            return adapter_parse_error_response(
                upstream_response.status_code,
                upstream_content_type,
                upstream_response.content,
                settings.max_error_preview_chars,
            )
        response_cleaned = True
        _log_request(request, started, model, target_model, stream_modified, passthrough, upstream_status, upstream_content_type, response_cleaned, None)
        return JSONResponse(status_code=upstream_response.status_code, content=payload)

    if should_clean:
        try:
            upstream_json = upstream_response.json()
            if not isinstance(upstream_json, dict):
                raise ValueError("upstream JSON is not an object")
        except ValueError:
            error_type = "adapter_parse_error"
            _log_request(request, started, model, target_model, stream_modified, passthrough, upstream_status, upstream_content_type, False, error_type)
            return adapter_parse_error_response(
                upstream_response.status_code,
                upstream_content_type,
                upstream_response.content,
                settings.max_error_preview_chars,
            )
        response_cleaned = True
        payload = sanitize_chat_completion_response(upstream_json, request_model=model)
        _log_request(request, started, model, target_model, stream_modified, passthrough, upstream_status, upstream_content_type, response_cleaned, None)
        return JSONResponse(status_code=upstream_response.status_code, content=payload)

    response = _passthrough_response(upstream_response)
    _log_request(request, started, model, target_model, stream_modified, passthrough, upstream_status, upstream_content_type, response_cleaned, None)
    return response


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def passthrough(full_path: str, request: Request) -> Response:
    del full_path
    settings: Settings = request.app.state.settings
    started = time.monotonic()
    raw_body = await request.body()

    try:
        upstream_response = await _forward_request(
            request=request,
            body=raw_body,
            force_json=False,
            settings=settings,
        )
    except UpstreamResponseTooLargeError:
        _log_request(request, started, "", False, False, True, None, "", False, "upstream_response_too_large")
        return upstream_response_too_large_response(settings.max_upstream_response_bytes)
    except httpx.RequestError:
        _log_request(request, started, "", False, False, True, None, "", False, "upstream_error")
        return upstream_error_response()

    upstream_content_type = upstream_response.headers.get("content-type", "")
    _log_request(
        request,
        started,
        "",
        False,
        False,
        True,
        upstream_response.status_code,
        upstream_content_type,
        False,
        None,
    )
    return _passthrough_response(upstream_response)


async def _forward_request(
    *,
    request: Request,
    body: bytes,
    force_json: bool,
    settings: Settings,
) -> httpx.Response:
    client: httpx.AsyncClient = request.app.state.client
    upstream_url = build_upstream_url(settings.sub2api_base_url, request.url.path)
    headers = build_upstream_headers(request.headers, force_json=force_json)
    params = list(request.query_params.multi_items())
    upstream_request = client.build_request(request.method, upstream_url, params=params, content=body, headers=headers)
    upstream_response = await client.send(upstream_request, stream=True)
    try:
        content = await _read_limited_response(upstream_response, settings.max_upstream_response_bytes)
    finally:
        await upstream_response.aclose()
    return httpx.Response(
        status_code=upstream_response.status_code,
        headers=upstream_response.headers,
        content=content,
        request=upstream_request,
    )


async def _read_limited_response(upstream_response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0

    async for chunk in upstream_response.aiter_bytes():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise UpstreamResponseTooLargeError
        chunks.append(chunk)

    return b"".join(chunks)


def _passthrough_response(upstream_response: httpx.Response) -> Response:
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=filter_response_headers(upstream_response.headers),
    )


def _log_prompt_preview(body: dict[str, object], max_chars: int) -> None:
    messages = body.get("messages")
    message_items = messages if isinstance(messages, list) else []
    system_prompts: list[str] = []
    user_prompts: list[str] = []

    for message in message_items:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in {"system", "user"}:
            continue

        content = message.get("content")
        preview = content if isinstance(content, str) else f"<non-string content: {type(content).__name__}>"
        if role == "system":
            system_prompts.append(preview)
        else:
            user_prompts.append(preview)

    system_preview, system_truncated = _prompt_preview(system_prompts, max_chars)
    user_preview, user_truncated = _prompt_preview(user_prompts, max_chars)
    model = body.get("model") if isinstance(body.get("model"), str) else "-"

    logger.info(
        format_log_fields(
            prompt_debug="true",
            model=model,
            messages_count=len(message_items),
            system_prompt_count=len(system_prompts),
            user_prompt_count=len(user_prompts),
            system_prompt_preview=system_preview,
            user_prompt_preview=user_preview,
            temperature=_format_prompt_log_value(body.get("temperature")),
            max_tokens=_format_prompt_log_value(body.get("max_tokens")),
            stream=_format_prompt_log_value(body.get("stream")),
            prompt_truncated=str(system_truncated or user_truncated).lower(),
        )
    )


def _prompt_preview(values: list[str], max_chars: int) -> tuple[str, bool]:
    if not values:
        return "-", False

    return _truncate_prompt(_escape_prompt_preview("\n---\n".join(values)), max_chars)


def _truncate_prompt(value: str, max_chars: int) -> tuple[str, bool]:
    safe_max_chars = max(1, max_chars)
    if len(value) <= safe_max_chars:
        return value, False
    return f"{value[:safe_max_chars]}...", True


def _escape_prompt_preview(value: str) -> str:
    return value.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def _format_prompt_log_value(value: object) -> object:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str | int | float):
        return value
    return f"<non-scalar value: {type(value).__name__}>"


def _log_request(
    request: Request,
    started: float,
    model: str,
    target_model: bool,
    stream_modified: bool,
    passthrough: bool,
    upstream_status: int | None,
    upstream_content_type: str,
    response_cleaned: bool,
    error_type: str | None,
) -> None:
    logger.info(
        format_log_fields(
            method=request.method,
            path=request.url.path,
            model=model or "-",
            authorization=mask_authorization(request.headers.get("authorization")) or None,
            target_model=str(target_model).lower(),
            passthrough=str(passthrough).lower(),
            stream_modified=str(stream_modified).lower(),
            upstream_status=upstream_status,
            upstream_content_type=upstream_content_type or "-",
            response_cleaned=str(response_cleaned).lower(),
            duration_ms=int((time.monotonic() - started) * 1000),
            error_type=error_type,
        )
    )
