"""`.env` mtime watcher — rescans when dotenv files change on disk.

Background daemon thread polls mtimes every few seconds; on change it runs the
normal scan() so fresh values enter the vault immediately instead of waiting
for the next tool call. Best-effort: thread failure never breaks the agent.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_INTERVAL_S = 5
_stop = threading.Event()
_thread: threading.Thread | None = None


def _dotenv_files(roots: list[Path]) -> list[Path]:
    out = []
    for root in roots:
        try:
            out.extend(root.rglob(".env*"))
        except Exception:
            continue
    return [p for p in out if p.is_file() and p.name.startswith(".env")]


def _loop(roots: list[Path], scan_fn) -> None:
    mtimes: dict[Path, float] = {}
    while not _stop.is_set():
        try:
            for f in _dotenv_files(roots):
                m = f.stat().st_mtime
                if mtimes.get(f) is None:
                    mtimes[f] = m
                elif m != mtimes[f]:
                    mtimes[f] = m
                    scan_fn()
                    logger.info("blindfold: %s changed; rescanned", f)
        except Exception:
            logger.debug("blindfold: watcher iteration failed", exc_info=True)
        _stop.wait(_INTERVAL_S)


def start(roots: list[Path], scan_fn) -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(roots, scan_fn),
                               name="blindfold-env-watch", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


__all__ = ["start", "stop"]
