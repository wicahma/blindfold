"""Tool-result secret discovery — catches secrets that never touch .env.

API responses carry fresh tokens in JSON bodies ("token": "abc..."). Core
discovery only reads files and process env; this module finds sensitive
key/value pairs inside arbitrary tool-result text using the SAME name gate
(core.SENSITIVE_NAME) so detection rules stay in one place.
"""
from __future__ import annotations

import re

from ...core import MIN_LEN, is_sensitive as core_is_sensitive

MAX_HAYSTACK = 200_000
MAX_CANDIDATES = 50

_PAIR_RES = (
    re.compile(r'["\']([A-Za-z_][A-Za-z0-9_]*)["\']\s*:\s*["\']([^"\']+)["\']'),
    re.compile(r'["\']?([A-Za-z_][A-Za-z0-9_]*)["\']?\s*=\s*["\']?([^\s"\',;}{]+)'),
)

_BORING_VALUE = re.compile(r"^(true|false|null|none|nan|\d+(\.\d+)?|v?\d+\.\d+.*)$", re.I)


def find_secrets(text: str) -> list[str]:
    if not text:
        return []
    hay = text[:MAX_HAYSTACK]
    found: list[str] = []
    seen = set()
    for rx in _PAIR_RES:
        for name, value in rx.findall(hay):
            if name in seen or value in seen:
                continue
            if len(value) < MIN_LEN or _BORING_VALUE.match(value):
                continue
            if not core_is_sensitive(name, value):
                continue
            seen.add(value)
            found.append(value)
            if len(found) >= MAX_CANDIDATES:
                return found
    return found


__all__ = ["find_secrets"]
