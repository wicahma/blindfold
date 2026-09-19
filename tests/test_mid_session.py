#!/usr/bin/env python3
"""Mid-session secret: fresh .env written after session start must be caught
once a file-reading tool runs (pre_tool_call rescan). Leak = text unchanged."""
import base64
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/diama/.hermes/hermes-agent")
sys.path.insert(0, "/home/diama/.hermes/plugins")
import agent.redact as redact  # noqa: E402
from blindfold.adapters.hermes import register_secrets, scan, _pre_tool_call  # noqa: E402

NEW = "FRESH_LEAK_TEST_abcdef1234567890"

redact.clear_vault_redaction_values()
tmp = Path(tempfile.mkdtemp())
(tmp / ".env").write_text(f"FRESH_API_KEY={NEW}\n")
os.chdir(tmp)

leak = redact.redact_sensitive_text(NEW) == NEW
print(f"1. before any scan, raw leaks: {leak}  (expect True)")
redact.clear_vault_redaction_values()

_pre_tool_call(tool="read_file", args_raw=str(tmp / ".env"))
raw_ok = redact.redact_sensitive_text(NEW) != NEW
b64_ok = redact.redact_sensitive_text(base64.b64encode(NEW.encode()).decode()) != base64.b64encode(NEW.encode()).decode()
rev_ok = redact.redact_sensitive_text(NEW[::-1]) != NEW[::-1]
print(f"2. after pre_tool_call(read_file): raw caught={raw_ok} base64 caught={b64_ok} reversed caught={rev_ok}  (expect all True)")
redact.clear_vault_redaction_values()

redact.clear_vault_redaction_values()
_pre_tool_call(tool="web_search", args_raw="x")
print(f"3. web_search skipped rescan, still leaks: {redact.redact_sensitive_text(NEW) == NEW}  (expect True)")

redact.clear_vault_redaction_values()
os.chdir("/home/diama")
sys.exit(0 if (raw_ok and b64_ok and rev_ok) else 1)
