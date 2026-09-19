"""Build a gateway handler from live secret discovery.

The one place the gateway adapter touches core. Everything else is masking on
bodies it is handed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...core import discover_all, transforms_of
from .litellm_hook import BlindfoldHandler


def build_handler(roots: Optional[list[Path]] = None, secrets: Optional[dict[str, str]] = None) -> BlindfoldHandler:
    """Discover secrets under roots (or use the passed map) and build a handler.

    Each registered value costs 1 + len(TRANSFORMS) slots; the handler carries
    raw + transforms so the scrub is form-invariant.
    """
    found = secrets if secrets is not None else discover_all(roots or [Path.cwd()])
    values: list[str] = []
    for value in found.values():
        if not value:
            continue
        values.append(value)
        values.extend(transforms_of(value))
    return BlindfoldHandler(secrets=values)
