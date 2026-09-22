"""Learned-value cache across gateway restarts.

Values discovered by transform_tool_result live in agent.redact's in-memory
bucket; a gateway restart drops them. This module keeps a plain list on disk
(mode 0600, same protection as the .env files themselves) and restores it at
register(). Only *learned* values are cached — file-sourced secrets re-scan
from disk anyway.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from . import vault

logger = logging.getLogger(__name__)

CACHE_PATH = Path.home() / ".blindfold" / "learned-values.txt"
_MAX_ENTRIES = 1000


def _read() -> list[str]:
    try:
        if CACHE_PATH.is_file():
            return [ln for ln in CACHE_PATH.read_text().splitlines() if ln]
    except Exception:
        logger.debug("blindfold: cache read failed", exc_info=True)
    return []


def _write(values: list[str]) -> None:
    try:
        CACHE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        CACHE_PATH.write_text("\n".join(values[-_MAX_ENTRIES:]) + "\n")
        os.chmod(CACHE_PATH, 0o600)
    except Exception:
        logger.debug("blindfold: cache write failed", exc_info=True)


def learn(value: str) -> bool:
    known = _read()
    if value in known:
        return False
    if not vault.learn_value(value):
        return False
    _write(known + [value])
    return True

def restore() -> int:
    return sum(1 for v in _read() if vault.learn_value(v))


__all__ = ["CACHE_PATH", "learn", "restore"]
