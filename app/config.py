from __future__ import annotations

import os
import math
from dataclasses import dataclass


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_prefixes(value: str | None) -> tuple[str, ...]:
    raw = value if value is not None else "grok"
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def parse_float(value: str | None, default: float, min_value: float | None = None) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    if not math.isfinite(parsed):
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


def parse_int(value: str | None, default: int, min_value: int | None = None) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


@dataclass(frozen=True)
class Settings:
    sub2api_base_url: str = "http://sub2api:8080"
    grok_model_prefixes: tuple[str, ...] = ("grok",)
    force_stream_false: bool = True
    clean_grok_response: bool = True
    passthrough_non_grok: bool = True
    log_level: str = "info"
    request_timeout: float = 120.0
    clean_all_responses: bool = False
    max_error_preview_chars: int = 1000
    max_upstream_response_bytes: int = 33_554_432
    max_sse_events: int = 4096
    max_sse_content_chars: int = 1_048_576


def load_settings() -> Settings:
    return Settings(
        sub2api_base_url=os.getenv("SUB2API_BASE_URL", "http://sub2api:8080").rstrip("/"),
        grok_model_prefixes=parse_prefixes(os.getenv("GROK_MODEL_PREFIXES")),
        force_stream_false=parse_bool(os.getenv("FORCE_STREAM_FALSE"), True),
        clean_grok_response=parse_bool(os.getenv("CLEAN_GROK_RESPONSE"), True),
        passthrough_non_grok=parse_bool(os.getenv("PASSTHROUGH_NON_GROK"), True),
        log_level=os.getenv("LOG_LEVEL", "info"),
        request_timeout=parse_float(os.getenv("REQUEST_TIMEOUT"), 120.0, min_value=0.001),
        clean_all_responses=parse_bool(os.getenv("CLEAN_ALL_RESPONSES"), False),
        max_error_preview_chars=parse_int(os.getenv("MAX_ERROR_PREVIEW_CHARS"), 1000, min_value=0),
        max_upstream_response_bytes=parse_int(os.getenv("MAX_UPSTREAM_RESPONSE_BYTES"), 33_554_432, min_value=1024),
        max_sse_events=parse_int(os.getenv("MAX_SSE_EVENTS"), 4096, min_value=1),
        max_sse_content_chars=parse_int(os.getenv("MAX_SSE_CONTENT_CHARS"), 1_048_576, min_value=1),
    )
