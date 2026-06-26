from __future__ import annotations

from app.config import load_settings, parse_float, parse_int


def test_parse_float_returns_default_for_invalid_or_out_of_range_values() -> None:
    assert parse_float("abc", 120.0, min_value=0.001) == 120.0
    assert parse_float("0", 120.0, min_value=0.001) == 120.0
    assert parse_float("nan", 120.0, min_value=0.001) == 120.0
    assert parse_float("30.5", 120.0, min_value=0.001) == 30.5


def test_parse_int_returns_default_for_invalid_or_out_of_range_values() -> None:
    assert parse_int("abc", 1000, min_value=0) == 1000
    assert parse_int("-1", 1000, min_value=0) == 1000
    assert parse_int("256", 1000, min_value=0) == 256


def test_load_settings_falls_back_for_invalid_numeric_environment(monkeypatch) -> None:
    monkeypatch.setenv("REQUEST_TIMEOUT", "invalid")
    monkeypatch.setenv("MAX_ERROR_PREVIEW_CHARS", "invalid")
    monkeypatch.setenv("MAX_UPSTREAM_RESPONSE_BYTES", "1")
    monkeypatch.setenv("MAX_SSE_EVENTS", "0")
    monkeypatch.setenv("MAX_SSE_CONTENT_CHARS", "0")

    settings = load_settings()

    assert settings.request_timeout == 120.0
    assert settings.max_error_preview_chars == 1000
    assert settings.max_upstream_response_bytes == 33_554_432
    assert settings.max_sse_events == 4096
    assert settings.max_sse_content_chars == 1_048_576
