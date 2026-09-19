"""Blindfold gateway masking — harness-agnostic request/response scrubbing.

Called by the LiteLLM CustomLogger hook and the standalone gateway. No harness
imports: give it a list of secret values and it masks them wherever they appear
in an OpenAI-compatible body. Structure is always preserved — a masked body must
still be a valid request the upstream can route.
"""
from __future__ import annotations

from typing import Any

# The sentinel emitted for a masked secret. Same shape across every adapter so a
# probe-suite check is comparable regardless of harness.
MASK = "[REDACTED]"


def _mask_str(text: str, values: list[str]) -> str:
    if not text or not values:
        return text
    # longest first: a secret never shadows a longer secret that contains it
    for v in sorted(values, key=len, reverse=True):
        if v and v in text:
            text = text.replace(v, MASK)
    return text


def _mask_any(obj: Any, values: list[str]) -> Any:
    if isinstance(obj, str):
        return _mask_str(obj, values)
    if isinstance(obj, list):
        return [_mask_any(item, values) for item in obj]
    if isinstance(obj, dict):
        return {k: _mask_any(v, values) for k, v in obj.items()}
    return obj


def mask_messages(body: dict, values: list[str]) -> dict:
    """Scrub secret values from an OpenAI-compatible request body."""
    if not isinstance(body, dict):
        return body
    return _mask_any(body, values)


def mask_response(resp: dict, values: list[str]) -> dict:
    """Scrub secret values from an OpenAI-compatible response body."""
    if not isinstance(resp, dict):
        return resp
    return _mask_any(resp, values)


# Alias kept for the standalone gateway's non-streaming path.
PROBE_SECRET = None
