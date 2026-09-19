"""Blindfold MCP companion server — JSON-RPC over stdio, zero dependencies.

⚠ COMPANION ONLY — NOT an enforcement layer.

MCP is client-mediated: the model decides which tool to call, and the server
cannot intercept any other tool call (spec 2026-07-28 RC, SEP-2577). This
server therefore never claims to stop a leak. Its only purpose is exposure:
a way to run discovery and probe from inside a chat that has no other
integration point (e.g. ChatGPT Desktop with no base-URL field).

Exposes two tools:
  blindfold_scan  — discover secrets under roots (returns names + counts)
  blindfold_probe — check whether a text contains a known secret in raw or
                    any registered transform form. Verdict: LEAK or OK.
                    No middle ground, same standard as the probe-suite.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

# This file is executed directly (stdio server), not as a package module.
_PKG_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PKG_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT.parent))

from blindfold.core import discover_all, transforms_of  # noqa: E402

PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "blindfold", "version": "1.0.0", "role": "companion"}


def _all_forms(secrets: list[str]) -> list[str]:
    vals: list[str] = []
    for s in secrets:
        if not s:
            continue
        vals.append(s)
        vals.extend(transforms_of(s))
    return vals


def _scan(roots: list[str]) -> str:
    paths = [Path(r) for r in roots] or [Path.cwd()]
    found = discover_all(paths)
    if not found:
        return "OK — no secrets discovered under " + ", ".join(str(p) for p in paths)
    lines = [f"{len(found)} secret(s) discovered:"]
    for name in sorted(found)[:50]:
        lines.append(f"  - {name}")
    if len(found) > 50:
        lines.append(f"  … and {len(found) - 50} more")
    lines.append("Registered values are masked before they reach the model context.")
    return "\n".join(lines)


def _probe(text: str, secrets: list[str]) -> str:
    values = _all_forms(secrets)
    for v in sorted(values, key=len, reverse=True):
        if v and v in text:
            return "LEAK — text contains a registered secret (raw or transformed form). Mask it before sending."
    return "OK — no registered secret found in text."


TOOLS = [
    {
        "name": "blindfold_scan",
        "description": "Discover secret-shaped values under the given roots (.env* files and process env). "
                       "Companion tool: reports what exists; does not modify anything.",
        "inputSchema": {
            "type": "object",
            "properties": {"roots": {"type": "array", "items": {"type": "string"},
                                     "description": "Directories to scan (default: cwd)"}},
        },
    },
    {
        "name": "blindfold_probe",
        "description": "Check whether a text contains a known secret in raw or any registered transform form "
                       "(base64/hex/reversed/url). Verdict: LEAK or OK. No middle ground.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to check"},
                "secrets": {"type": "array", "items": {"type": "string"},
                            "description": "Known secret values (raw) to test against"},
            },
            "required": ["text"],
        },
    },
]


def handle(payload: dict) -> dict | None:
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return None
    rid = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }}
    if method == "notifications/initialized":
        return None  # notification, no response
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args: dict[str, Any] = params.get("arguments") or {}
        try:
            if name == "blindfold_scan":
                out = _scan(args.get("roots") or [])
            elif name == "blindfold_probe":
                out = _probe(args.get("text", ""), args.get("secrets") or [])
            else:
                return {"jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32601, "message": f"unknown tool: {name}"}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": out}]}}

    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"unknown method: {method}"}}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(payload)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
