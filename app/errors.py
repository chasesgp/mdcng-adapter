from __future__ import annotations

from fastapi.responses import JSONResponse


def invalid_json_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": "invalid json request body",
                "type": "invalid_request_error",
            }
        },
    )


def upstream_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": "upstream request failed",
                "type": "upstream_error",
            }
        },
    )


def upstream_response_too_large_response(max_bytes: int) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": "upstream response too large",
                "type": "upstream_response_too_large",
                "max_bytes": max_bytes,
            }
        },
    )


def adapter_parse_error_response(
    upstream_status: int,
    upstream_content_type: str,
    upstream_body: bytes,
    max_preview_chars: int,
) -> JSONResponse:
    preview = upstream_body.decode("utf-8", errors="replace")[:max_preview_chars]
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": "adapter failed to parse upstream response",
                "type": "adapter_parse_error",
                "upstream_status": upstream_status,
                "upstream_content_type": upstream_content_type,
                "upstream_body_preview": preview,
            }
        },
    )
