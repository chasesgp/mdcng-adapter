from __future__ import annotations

from collections.abc import Mapping


REQUEST_HEADER_ALLOWLIST = {
    "authorization",
    "content-type",
    "accept",
    "openai-beta",
    "user-agent",
}

CANONICAL_REQUEST_HEADERS = {
    "authorization": "Authorization",
    "content-type": "Content-Type",
    "accept": "Accept",
    "openai-beta": "OpenAI-Beta",
    "user-agent": "User-Agent",
}

DROP_RESPONSE_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def build_upstream_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def build_upstream_headers(headers: Mapping[str, str], force_json: bool = False) -> dict[str, str]:
    upstream_headers: dict[str, str] = {}
    for key, value in headers.items():
        normalized = key.lower()
        if normalized not in REQUEST_HEADER_ALLOWLIST:
            continue
        if force_json and normalized == "content-type":
            continue
        upstream_headers[CANONICAL_REQUEST_HEADERS[normalized]] = value

    upstream_headers["Accept-Encoding"] = "identity"
    if force_json:
        upstream_headers["Content-Type"] = "application/json"

    return upstream_headers


def filter_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() not in DROP_RESPONSE_HEADERS}
