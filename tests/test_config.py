from __future__ import annotations

from app.config import load_settings, parse_bool, parse_float, parse_int


def test_parse_bool_accepts_debug_prompt_values() -> None:
    assert parse_bool("true", False) is True
    assert parse_bool("false", True) is False
    assert parse_bool("invalid", False) is False


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
    monkeypatch.setenv("DEBUG_LOG_PROMPT_MAX_CHARS", "0")
    monkeypatch.setenv("DEBUG_LOG_REQUEST_BODY_MAX_CHARS", "0")
    monkeypatch.setenv("DEBUG_LOG_RESPONSE_BODY_MAX_CHARS", "0")

    settings = load_settings()

    assert settings.request_timeout == 120.0
    assert settings.max_error_preview_chars == 1000
    assert settings.max_upstream_response_bytes == 33_554_432
    assert settings.max_sse_events == 4096
    assert settings.max_sse_content_chars == 1_048_576
    assert settings.debug_log_prompt_max_chars == 1000
    assert settings.debug_log_request_body_max_chars == 4000
    assert settings.debug_log_response_body_max_chars == 4000


def test_load_settings_reads_prompt_debug_environment(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG_LOG_PROMPT", "true")
    monkeypatch.setenv("DEBUG_LOG_PROMPT_MAX_CHARS", "256")
    monkeypatch.setenv("DEBUG_LOG_REQUEST_BODY", "true")
    monkeypatch.setenv("DEBUG_LOG_REQUEST_BODY_MAX_CHARS", "512")
    monkeypatch.setenv("DEBUG_LOG_RESPONSE_BODY", "true")
    monkeypatch.setenv("DEBUG_LOG_RESPONSE_BODY_MAX_CHARS", "1024")

    settings = load_settings()

    assert settings.debug_log_prompt is True
    assert settings.debug_log_prompt_max_chars == 256
    assert settings.debug_log_request_body is True
    assert settings.debug_log_request_body_max_chars == 512
    assert settings.debug_log_response_body is True
    assert settings.debug_log_response_body_max_chars == 1024


def test_load_settings_defaults_prompt_debug_to_disabled(monkeypatch) -> None:
    monkeypatch.delenv("DEBUG_LOG_PROMPT", raising=False)
    monkeypatch.delenv("DEBUG_LOG_PROMPT_MAX_CHARS", raising=False)

    settings = load_settings()

    assert settings.debug_log_prompt is False
    assert settings.debug_log_prompt_max_chars == 1000
    assert settings.debug_log_request_body is False
    assert settings.debug_log_request_body_max_chars == 4000
    assert settings.debug_log_response_body is False
    assert settings.debug_log_response_body_max_chars == 4000
