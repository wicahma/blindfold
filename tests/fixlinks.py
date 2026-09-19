#!/usr/bin/env python3
"""Rewrite SilverBullet wiki links to absolute when a file moved across folders.

Dry-run by default; pass --apply to write. Prints before/after per change.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/diama/notes/blindfold")
APPLY = "--apply" in sys.argv

# Existing pages, relative to ROOT, without extension (SilverBullet page identity).
PAGES = sorted(
    (p.relative_to(ROOT).with_suffix("").as_posix())
    for p in ROOT.rglob("*.md")
    if p != ROOT / "README.md"  # README resolves as ROOT itself
)
# Match a page name (no slash) or "README" or "folder/page" — everything that is
# NOT already absolute (already-absolute links contain a slash and we never
# wrote one in blindfold/, so "no slash" is the reliable signal here).
SLASHLESS = re.compile(r"\[\[([^\]|#]+)(?=[\]|#])")

changes = []
for page in PAGES:
    f = ROOT / f"{page}.md"
    text = f.read_text()
    folder = f.parent.relative_to(ROOT).as_posix()

    def fix(m):
        target = m.group(1)
        if target in ("README",):
            new = "blindfold/README" if folder != "." else "README"
        else:
            hits = [p for p in PAGES if p.rsplit("/", 1)[-1] == target]
            if len(hits) != 1:
                return m.group(0)  # ambiguous/unknown — leave alone
            new = f"blindfold/{hits[0]}"
        if folder != ".":
            old = m.group(0)
            return old.replace(f"[[{target}", f"[[{new}", 1)
        return m.group(0)

    out = SLASHLESS.sub(fix, text)
    if out != text:
        changes.append((f, text, out))

print(f"pages: {len(PAGES)}  changes: {len(changes)}  apply={APPLY}")
for f, _, _ in changes:
    print(f"  {f.relative_to(ROOT)}")
if APPLY:
    for f, _, out in changes:
        f.write_text(out)
    print("written.")
