from __future__ import annotations

import logging
import sys


def setup_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )


def mask_authorization(value: str | None) -> str:
    if not value:
        return ""

    parts = value.strip().split(" ", 1)
    if len(parts) == 2:
        scheme, token = parts
    else:
        scheme, token = "Bearer", parts[0]

    if not token:
        return f"{scheme} ****"

    suffix = token[-4:] if len(token) > 4 else "****"
    if token.startswith("sk-"):
        return f"{scheme} sk-****{suffix}"
    return f"{scheme} ****{suffix}"


def format_log_fields(**fields: object) -> str:
    return " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
