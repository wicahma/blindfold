"""Blindfold Amazon Q CLI hook adapter — block-only enforcement.

Amazon Q CLI has NO base-URL override, so the hook is the only interception
surface. Q CLI hooks cannot modify content — they can only abort the tool call
by exiting with code 2 and printing a reason to stderr.

Install into ~/.aws/amazonq/cli-agents/<agent>.json:
    {
      "hooks": {
        "PreToolUse": [
          {"command": ["python3", "/path/to/blindfold/adapters/qcli/hook.py"]}
        ]
      }
    }

Secrets are passed via the BLINDFOLD_VALUES env var (newline-separated,
pre-transformed by core.transforms_of) so no secret is ever parsed from disk
inside the hook process itself.
"""
from __future__ import annotations

import json
import sys


def _values() -> list[str]:
    raw = __import__("os").environ.get("BLINDFOLD_VALUES", "")
    return [v for v in raw.split("\n") if v]


def _contains_secret(text: str, values: list[str]) -> bool:
    for v in sorted(values, key=len, reverse=True):
        if v and v in text:
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Not a hook payload we understand — fail safe: allow
        return 0

    values = _values()
    if not values:
        return 0

    tool_input = payload.get("toolInput") or {}
    if isinstance(tool_input, dict):
        blob = json.dumps(tool_input)
    else:
        blob = str(tool_input)

    if _contains_secret(blob, values):
        print(
            "blindfold: blocked tool call — a registered secret was detected in "
            "the tool input. Secret values are not permitted to leave the "
            "session. See blindfold/core for the discovery + transform registry.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
