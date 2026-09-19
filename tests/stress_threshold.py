#!/usr/bin/env python3
"""Stress the vault bucket: register 300 fake secrets via the plugin path and
assert every one of them (raw + transforms) survives redaction — no LRU eviction."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, "/home/diama/.hermes/hermes-agent")
sys.path.insert(0, "/home/diama/.hermes/plugins")
import agent.redact as redact  # noqa: E402
import blindfold  # noqa: E402

redact.clear_vault_redaction_values()
orig = redact._VAULT_REDACTION_MAX_PER_PROFILE

N = 300
secrets = {f"FAKE_KEY_{i:04d}": f"secret-value-{i:04d}-padding-xxxxxxxxxxxxx" for i in range(N)}
n = blindfold.register_secrets(secrets)
print(f"registered {n}/{N}")
print(f"threshold: {orig} -> {redact._VAULT_REDACTION_MAX_PER_PROFILE}")

lost = []
for i in range(N):
    v = secrets[f"FAKE_KEY_{i:04d}"]
    probes = {"raw": v, "base64": base64.b64encode(v.encode()).decode(),
              "hex": v.encode().hex(), "rev": v[::-1]}
    for pn, t in probes.items():
        if redact.redact_sensitive_text(t) == t:
            lost.append(f"FAKE_KEY_{i:04d}.{pn}")

print(f"LOST (evicted): {len(lost)}")
for f in lost[:10]:
    print("  LOST", f)
redact.clear_vault_redaction_values()
sys.exit(1 if lost else 0)
