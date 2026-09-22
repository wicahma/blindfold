"""Hermes hook callbacks — thin wiring between Hermes hook payloads and core.

Every hook: scan/learn first (so fresh secrets enter the vault), then mask with
the harness's own exact-substring scrub. Returning None defers to other hooks.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from ...core import discover_all
from . import persist, scanner, vault

logger = logging.getLogger(__name__)

_FILE_TOOLS = frozenset({"read_file", "read_files", "cat", "terminal",
                         "execute_code", "bash", "shell", "web_extract"})


def scan_roots(cwd: Path, hermes_home: str | Path | None) -> list[Path]:
    roots = [Path(cwd)]
    if hermes_home:
        roots.append(Path(hermes_home))
    return roots


def scan(cwd: Path | None = None, hermes_home: str | Path | None = None, **_kw) -> dict:
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    if hermes_home is None:
        hermes_home = os.environ.get("HERMES_HOME")
    secrets = discover_all(scan_roots(cwd, hermes_home))
    vault.raise_bucket_cap()
    n = vault.register_secrets(secrets)
    logger.info("blindfold: registered %d secret(s) (+ transforms) from %d source(s)",
                n, len(secrets))
    return {"registered": n, "sources": len(secrets)}


def _pre_tool_call(*, tool: str = "", tool_name: str = "", **_kwargs) -> None:
    name = (tool or tool_name or "").lower()
    if not name or name not in _FILE_TOOLS:
        return
    try:
        scan()
    except Exception:
        logger.debug("blindfold: pre_tool_call rescan failed", exc_info=True)


def _transform_tool_result(*, result=None, **_kw):
    if not isinstance(result, str) or not result:
        return None
    try:
        import agent.redact as redact
        for value in scanner.find_secrets(result):
            persist.learn(value)
        masked = redact.redact_registered_vault_values(result)
        return masked if masked != result else None
    except Exception:
        logger.debug("blindfold: tool-result transform failed", exc_info=True)
        return None


def _transform_terminal_output(*, output: str = "", command: str = "", **_kw):
    if not output:
        return None
    try:
        scan()
        masked = vault.redact_text(output)
        return masked if masked != output else None
    except Exception:
        logger.debug("blindfold: terminal transform failed", exc_info=True)
        return None


def _transform_llm_output(*, response_text: str = "", **_kw):
    if not response_text:
        return None
    try:
        res = scan()
    except Exception:
        return None
    n_vals = vault.vault_size()
    src = res.get("sources", 0)
    reg = res.get("registered", 0)
    vault_info = f", {n_vals} vault slots" if isinstance(n_vals, int) else ""
    footer = (f"\n\n---\n🛡 blindfold: active — {reg} secret(s) registered "
              f"from {src} source(s){vault_info}")
    return response_text + footer


__all__ = ["scan_roots", "scan", "_pre_tool_call", "_transform_tool_result",
           "_transform_terminal_output", "_transform_llm_output"]
