#!/usr/bin/env python3
"""E2E check: fire blindfold's real session hooks, then re-probe the real
~/.hermes/.env values that leaked before. Prints leak status only — never a value.

Also asserts the plugin's hooks are actually wired (a session hook with no runtime
fire-site is a silent no-op — that's the bug this script catches)."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, "/home/diama/.hermes/hermes-agent")
from hermes_cli.plugins import PluginManager  # noqa: E402
from agent.redact import redact_sensitive_text, clear_vault_redaction_values  # noqa: E402

pm = PluginManager()
pm.discover_and_load()

SESSION_HOOKS = ("on_session_reset", "on_session_finalize")
for h in SESSION_HOOKS + ("pre_tool_call",):
    cbs = list(pm.iter_hook_callbacks(h))
    print(f"hook {h}: {len(cbs)} cb")
    assert cbs, f"NO HOOK REGISTERED for {h} — secret scan would silently never run"

for h in SESSION_HOOKS:
    for cb in pm.iter_hook_callbacks(h):
        print(f"scan ({h}):", cb(session_id="probe", platform="cli", reason="new_session"))
print()

envf = Path.home() / ".hermes" / ".env"
leaks = []
for line in envf.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    v = v.strip().strip("\"'").strip()
    if len(v) < 8:
        continue
    probes = {
        "raw": v,
        "base64": base64.b64encode(v.encode()).decode(),
        "hex": v.encode().hex(),
        "rev": v[::-1],
    }
    for pn, t in probes.items():
        if redact_sensitive_text(t) == t:
            leaks.append(f"{k}.{pn}")

print(f"LEAKS REMAINING: {len(leaks)}")
for f in leaks:
    print("  LEAK", f)
clear_vault_redaction_values()
