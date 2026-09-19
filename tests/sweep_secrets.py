#!/usr/bin/env python3
"""Pre-push secret sweep for the blindfold repo.
Catches high-entropy strings, not patterns — the thing a real scanner would find.
Fails on any hit that is NOT in the known-fixture allowlist."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOW = {
    "4a8b9c2d1e7f3a5b6c8d9e0f1a2b3c4d567890abcdef1234567890abcdef1234",
    "c2stYW50LWFhYTEyMzQ1Njc4OTBxd2VydHl1aW9wYXNkZmdoamts",
    "c2stYW50LWFhYTEyMzQ1Njc4OTBhd2VydHl1aW9wYXNkZmdoamts",
    "a1f3b5c7d9e2f4a6b8c0d1e3f5a7b9c1e3d5f7a9",
    "a1f3b5c7d9e2f4a6b8c0d1e3f5a7b9c1e3d5f7a9deadbeef",
    "deafbeefcafebabe1234567890abcdef",
    "0xdeafbeefcafebabe1234567890abcdef",
    "51HbXyZabcDEFghiJKLmnopQRSTuvwxYZ0123456789",
    "awssecret_placeholder",
    "sk-ant-aaa1234567890qwertyuiopasdfghjkl",
    "aaa1234567890qwertyuiopasdfghjkl",
}
NOISE = ("hmac/hashlib", "Read/Bash", "AWS/Slack", "com/orgs", "com/wicahma",
         "GitLab(13", "Google/Stripe")

HEX = re.compile(r"\b[A-Za-z0-9+/=]{32,}\b")
TOKEN = re.compile(r"\b(?:sk|gh[pousrt]|xox[abprs]|AKIA|eyJ)[A-Za-z0-9_\-]{16,}\b")

hits = []
for p in sorted(ROOT.rglob("*")):
    if not p.is_file() or any(x in p.parts for x in (".git", "__pycache__")):
        continue
    for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
        toks = set()
        for t in re.split(r"[^A-Za-z0-9+/]", line):
            if len(t) >= 16:
                toks.add(t)
                toks.add(t.lstrip("0x"))
        for m in [x for x in toks if (HEX.fullmatch(x) or TOKEN.fullmatch(x))]:
            if m in ALLOW or any(n in m for n in NOISE):
                continue
            hits.append(f"{p.relative_to(ROOT)}:{i}: {m[:24]}...")

print(f"suspicious findings: {len(hits)}")
for h in hits[:20]:
    print("  ", h)
sys.exit(1 if hits else 0)
