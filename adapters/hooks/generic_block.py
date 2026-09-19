"""Blindfold generic block-only hook — one script, every JSON-stdin harness.

Claude Code, Codex CLI, Cline, Cursor, Windsurf and Amazon Q CLI all pipe a
JSON payload to a hook process and abort the tool call when it exits 2. Their
schemas differ; the check does not: recursively scan every string in the
payload for a registered secret (raw or any transform form).

These hooks CANNOT rewrite content — block-only is the contract. Masking is
the gateway's job; this shim adds local blocking policy where a gateway is
not applicable (or as defense-in-depth).

Register per harness:
  Claude Code  ~/.claude/settings.json       hooks.PreToolUse
  Codex CLI    ~/.codex/config.toml          [hooks] pre_tool_use
  Cline        .clinerules/hooks/README.md   script without extension
  Cursor       ~/.cursor/hooks.json          hooks array
  Windsurf     /etc/windsurf/hooks.json      hooks array (root-owned)
  Amazon Q CLI ~/.aws/amazonq/cli-agents/*.json  hooks.PreToolUse

Secrets arrive via BLINDFOLD_VALUES (newline-separated, raw + transforms,
prepared once by core.transforms_of at registration time).
"""
from __future__ import annotations

import json
import os
import sys


def _values() -> list[str]:
    raw = os.environ.get("BLINDFOLD_VALUES", "")
    return [v for v in raw.split("\n") if v]


def _strings(obj, out: list[str]) -> None:
    """Collect every string value, wherever it hides in the payload."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _strings(v, out)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # not a hook payload we understand — fail safe: allow

    values = _values()
    if not values:
        return 0

    strings: list[str] = []
    _strings(payload, strings)
    blob = "\n".join(strings)

    for v in sorted(values, key=len, reverse=True):
        if v and v in blob:
            tool = payload.get("tool_name") or payload.get("toolName") or "call"
            print(
                f"blindfold: blocked {tool} — a registered secret was detected "
                f"in the tool input (raw or transformed form). See blindfold/core.",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
