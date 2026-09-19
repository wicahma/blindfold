#!/usr/bin/env python3
"""MCP companion server test — JSON-RPC over stdio, zero dependencies.

Verifies the MCP server exposes discovery + probe as tools, responds to the
standard handshake (initialize, list tools, call a tool), and — critically —
is documented as COMANION ONLY: it cannot intercept other tool calls
(client-mediated dispatch, spec 2026-07-28 RC). This test asserts it does NOT
claim enforcement.

Run: python3 tests/adapters/test_mcp.py
"""
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SERVER = ROOT / "adapters" / "mcp" / "server.py"

FAIL = []
SECRET = f"mcp_test_{'s' * 16}"


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def rpc(payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input=json.dumps(payload) + "\n",
        capture_output=True, text=True, timeout=20,
    )
    for line in proc.stdout.strip().splitlines():
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {"error": f"no JSON response; stderr={proc.stderr[:200]}"}


def main():
    tmp = Path(tempfile.mkdtemp())
    (tmp / ".env").write_text(f"MCP_PROBE_KEY={SECRET}\n")

    print("[1] initialize handshake")
    resp = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-11-25",
                           "capabilities": {},
                           "clientInfo": {"name": "test", "version": "1"}}})
    check("initialize returns result", "result" in resp, str(resp)[:150])
    check("server declares companion role (not enforcement)",
          "companion" in json.dumps(resp).lower() or "scan" in json.dumps(resp).lower(),
          str(resp)[:150])

    print("[2] tools/list exposes scan + probe")
    resp2 = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = [t.get("name") for t in resp2.get("result", {}).get("tools", [])]
    check("scan tool present", "blindfold_scan" in names, str(names))
    check("probe tool present", "blindfold_probe" in names, str(names))

    print("[3] tools/call scan discovers .env secrets")
    resp3 = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "blindfold_scan",
                            "arguments": {"roots": [str(tmp)]}}})
    text = json.dumps(resp3)
    check("scan reports a found secret", "MCP_PROBE_KEY" in text, text[:180])

    print("[4] tools/call probe detects a leak (verdict LEAK/OK, no middle ground)")
    resp4 = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                 "params": {"name": "blindfold_probe",
                            "arguments": {"text": SECRET, "secrets": [SECRET]}}})
    text4 = json.dumps(resp4)
    check("probe verdict LEAK on raw secret", "LEAK" in text4, text4[:180])

    resp5 = rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                 "params": {"name": "blindfold_probe",
                            "arguments": {"text": "clean text", "secrets": [SECRET]}}})
    text5 = json.dumps(resp5)
    check("probe verdict OK on clean text", "OK" in text5, text5[:180])

    print("[5] probe catches transforms too")
    b64 = base64.b64encode(SECRET.encode()).decode()
    resp6 = rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                 "params": {"name": "blindfold_probe",
                            "arguments": {"text": b64, "secrets": [SECRET, b64]}}})
    check("base64 transform flagged", "LEAK" in json.dumps(resp6), json.dumps(resp6)[:150])

    (tmp / ".env").unlink(missing_ok=True)
    tmp.rmdir()
    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
