from __future__ import annotations

from app.logging_config import mask_authorization
from app.proxy import build_upstream_headers, build_upstream_url, filter_response_headers


def test_build_upstream_url() -> None:
    assert build_upstream_url("http://sub2api:8080/", "/v1/models") == "http://sub2api:8080/v1/models"


def test_build_upstream_headers_filters_and_canonicalizes() -> None:
    headers = {
        "authorization": "Bearer sk-secretabcd",
        "content-type": "text/plain",
        "accept": "application/json",
        "host": "adapter",
        "content-length": "100",
        "connection": "keep-alive",
    }

    upstream_headers = build_upstream_headers(headers, force_json=True)

    assert upstream_headers == {
        "Authorization": "Bearer sk-secretabcd",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
    }


def test_filter_response_headers_drops_hop_by_hop_headers() -> None:
    filtered = filter_response_headers(
        {
            "content-type": "application/json",
            "content-length": "10",
            "transfer-encoding": "chunked",
            "x-request-id": "abc",
        }
    )

    assert filtered == {"content-type": "application/json", "x-request-id": "abc"}


def test_mask_authorization() -> None:
    assert mask_authorization("Bearer sk-secretabcd") == "Bearer sk-****abcd"
    assert mask_authorization("token-value") == "Bearer ****alue"
