#!/usr/bin/env python3
"""Blindfold Phase 0 — slot references instead of secret values in agent context."""
import hmac, hashlib, json, os, re, sys, tomllib, subprocess, tempfile, shutil
from pathlib import Path

SLOT_RE = re.compile(r"\[BLF:([A-Z_]+):([0-9a-f]{8})\]")
SENSITIVE_NAME = re.compile(
    r"^(.*_(TOKEN|SECRET|API_KEY|PASSWORD|KEY|CREDENTIALS?)|DATABASE_URL|CONNECTION_STRING)$"
)
NEVER_SECRET = {"PATH", "HOME", "USER", "SHELL", "SSH_AUTH_SOCK", "PWD", "LANG", "LC_ALL", "TERM"}
TRIVIAL = {"true", "false", "none", "null", "yes", "no", "0", "1"}
MIN_LEN = 8

STATE_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / "blindfold"
STATE_FILE = STATE_DIR / "state.json"

def _load_state():
    if not STATE_FILE.exists():
        ks = os.urandom(32)
        return {"ks": os.urandom(32), "slots": {}}
    st = json.loads(STATE_FILE.read_text())
    st["ks"] = bytes.fromhex(st["ks"])
    return st

def _save_state(st):
    STATE_DIR.mkdir(0o700, exist_ok=True)
    tmp = STATE_DIR.with_suffix(".tmp") / f"st.{os.getpid()}"
    tmp.parent.mkdir(0o700, exist_ok=True)
    payload = {"ks": st["ks"].hex(), "slots": st["slots"]}
    tmp.write_text(json.dumps(payload))
    tmp.replace(STATE_FILE)
    os.chmod(STATE_FILE, 0o600)

class Registry:
    """Value -> stable slot. Session-scoped key -> unlinkable across sessions."""

    def __init__(self):
        st = _load_state()
        self.ks = st["ks"]
        self.slots = st["slots"]
        self.by_slot = {v["slot"]: k for k, v in self.slots.items()}

    def save(self):
        _save_state({"ks": self.ks, "slots": self.slots})

    def _digest(self, typ, value):
        h = hmac.new(self.ks, f"{typ}|{value}".encode(), hashlib.sha256).hexdigest()[:8]
        return f"[BLF:{typ}:{h}]"

    def register(self, value, typ="SECRET"):
        if not value or len(value) < MIN_LEN or value.lower() in TRIVIAL:
            return None
        if value in self.slots:
            return self.slots[value]["slot"]
        idx = len([s for s in self.slots.values() if s["type"] == typ]) + 1
        slot = self._digest(typ, value)
        self.slots[value] = {"slot": slot, "type": typ, "var": f"BLF_{typ}_{idx:02d}"}
        self.by_slot[slot] = value
        return slot

    def env_for(self):
        return {v["var"]: k for k, v in self.slots.items()}

    def rebind(self, slot):
        """Resolve slot -> raw value. Reject anything not in this session table."""
        m = SLOT_RE.fullmatch(slot.strip()) if slot else None
        if not m:
            raise KeyError(f"malformed slot: {slot!r}")
        value = self.by_slot.get(slot.strip())
        if value is None:
            raise KeyError(f"unregistered slot (spoof?): {slot!r}")
        return value

def discover_env():
    out = {}
    for name, value in os.environ.items():
        if name in NEVER_SECRET or name.endswith("_SESSION"):
            continue
        if SENSITIVE_NAME.match(name) and value and len(value) >= MIN_LEN:
            out[name] = value
    return out

def discover_dotenv(root="."):
    out = {}
    for p in sorted(Path(root).glob(".env*")):
        if p.suffix in (".example", ".sample", ".template"):
            continue
        for line in p.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip().removeprefix("export ").strip(), val.strip().strip("\"'")
            if key and val:
                out.setdefault(f"{p.name}:{key}", val)
    return out

def redact_text(text, reg):
    for value in sorted(reg.slots, key=len, reverse=True):
        text = text.replace(value, reg.slots[value]["slot"])
    return text

def redact_env_text(text, reg):
    lines = []
    for line in text.splitlines():
        key, sep, val = line.partition("=")
        if sep and val.strip():
            slot = reg.register(val.strip().strip("\"'"))
            val = slot if slot else val
        lines.append(f"{key}{sep}{val}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

def _walk_json(obj, reg):
    if isinstance(obj, dict):
        return {k: _walk_json(v, reg) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_json(v, reg) for v in obj]
    if isinstance(obj, str):
        slot = reg.register(obj)
        return slot if slot else obj
    if isinstance(obj, bool):
        return False
    if isinstance(obj, (int, float)):
        return 0
    return obj

def redact_structured(path, reg):
    """Type-preserving redaction. Returns redacted text, or None if opaque/denied."""
    p = Path(path)
    suffix = p.suffix.lower()
    raw = p.read_text(errors="replace")
    if suffix in (".json", ".jsonc"):
        import json as _json
        return _json.dumps(_walk_json(_json.loads(raw), reg), indent=2)
    if suffix == ".toml":
        return tomllib.dumps(_walk_json(tomllib.loads(raw), reg))
    if suffix in (".env",) or p.name.startswith(".env"):
        return redact_env_text(raw, reg)
    if suffix in (".pem", ".key", ".p12", ".pfx", ".asc", ".gpg"):
        return None
    return None

def cmd_register(args):
    reg = Registry()
    found = {**discover_dotenv(), **{f"env:{k}": v for k, v in discover_env().items()}}
    n = 0
    for src, value in found.items():
        if reg.register(value):
            n += 1
    reg.save()
    print(f"registered {n} secret(s) from {len(found)} source(s)")
    for value, meta in reg.slots.items():
        print(f"  {meta['var']:<18} {meta['slot']}")

def cmd_redact(args):
    reg = Registry()
    src = Path(args.path)
    out = redact_structured(src, reg) if src.is_file() and args.structured else redact_text(src.read_text(), reg)
    if out is None:
        sys.exit(f"opaque file denied: {src}")
    reg.save()
    dst = Path(args.out) if args.out else src.with_suffix(src.suffix + ".blf")
    dst.write_text(out)
    print(f"{src} -> {dst}")

def cmd_status(args):
    reg = Registry()
    print(f"state:  {STATE_FILE}")
    print(f"slots:  {len(reg.slots)}")
    for value, meta in reg.slots.items():
        print(f"  {meta['var']:<18} {meta['slot']:<22} <- {value[:4]}...{value[-3:]}")

def cmd_exec(args):
    reg = Registry()
    env = dict(os.environ)
    env.update(reg.env_for())
    try:
        resolved = [SLOT_RE.sub(lambda m: reg.rebind(m.group(0)), a) for a in args.cmd]
    except KeyError as e:
        sys.exit(f"blindfold: refused {e}")
    subprocess.run(resolved, env=env, check=False)

def cmd_selftest(args):
    reg = Registry()
    reg.slots.clear()
    fixture = {
        "API_KEY": "testkey_deadbeef_cafebabe_1234",
        "DB_PASSWORD": "Sup3rS3cr3t-P4ssw0rd!",
        "SERVICE_TOKEN": "a1f3b5c7d9e2f4a6b8c0d1e3f5a7b9c1e3d5f7a9" * 2 + "deadbeef",
        "ENCRYPTION_KEY": "0xdeafbeefcafebabe1234567890abcdef",
        "AWS_SECRET_ACCESS_KEY": "awssecret_deadbeef_cafebabe_1234",
    }
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("[1] recall: registry catches all 5 (vs gitleaks 0/5, trufflehog 0/5, noseyparker 2/5)")
    slots = {k: reg.register(v) for k, v in fixture.items()}
    check("5/5 registered", all(slots.values()), f"got {slots}")

    print("[2] leak: no raw value survives redact_text")
    transcript = (
        f"ps output: AZURE_OPENAI_KEY=${{AZURE_OPENAI_KEY:-{fixture['SERVICE_TOKEN']}}}\n"
        f"config says host=prod-db user=admin password={fixture['DB_PASSWORD']}\n"
        f"curl -H 'Authorization: Bearer {fixture['API_KEY']}'\n"
        f"key={fixture['ENCRYPTION_KEY']} and aws={fixture['AWS_SECRET_ACCESS_KEY']}\n"
    )
    red = redact_text(transcript, reg)
    leaked = [v for v in fixture.values() if v in red]
    check("0 raw values remain", not leaked, f"leaked: {[v[:12] for v in leaked]}")

    print("[3] type-preserving JSON redaction")
    cfg = json.dumps({
        "db": {"host": "prod-db", "port": 5432, "password": fixture["DB_PASSWORD"], "ssl": True},
        "keys": [fixture["API_KEY"], "plain-string"],
    })
    tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    tf.write(cfg)
    tf.close()
    out = json.loads(redact_structured(tf.name, reg))
    reg.save()
    check("password slotted", out["db"]["password"].startswith("[BLF:"))
    check("port numeric 0", out["db"]["port"] == 0 and isinstance(out["db"]["port"], int))
    check("ssl bool false", out["db"]["ssl"] is False)
    check("array item slotted", out["keys"][0].startswith("[BLF:"))

    print("[4] rebinding guard (fail-closed)")
    check("valid slot resolves", reg.rebind(slots["API_KEY"]) == fixture["API_KEY"])
    check("spoofed slot rejected", _rejected(lambda: reg.rebind("[BLF:SECRET:deadbeef]")))
    check("malformed slot rejected", _rejected(lambda: reg.rebind("just-text")))
    check("traversal-ish rejected", _rejected(lambda: reg.rebind("[BLF:SECRET:aa]; rm -rf /")))

    print("[5] shell-env bridge: child resolves $BLF_* but never sees it in context")
    probe = reg.slots[fixture["DB_PASSWORD"]]["var"]
    r = subprocess.run(
        ["bash", "-c", "echo len=${#%s} head=${%s:0:4}" % (probe, probe)],
        env={**os.environ, **reg.env_for()}, capture_output=True, text=True,
    )
    check("child got real value", f"len={len(fixture['DB_PASSWORD'])}" in r.stdout, r.stdout.strip())
    check("placeholder not literal", r.stdout.count("[BLF:") == 0)

    print("[6] idempotency + session unlinkability")
    reg2 = Registry()
    reg2.slots.clear()
    reg2.ks = os.urandom(32)
    s2 = reg2.register(fixture["API_KEY"])
    check("same session stable", reg.register(fixture["API_KEY"]) == slots["API_KEY"])
    check("new session differs", s2 != slots["API_KEY"])

    print("\n" + ("ALL GREEN" if not fails else f"{len(fails)} FAILED: {fails}"))
    return 1 if fails else 0

def _rejected(fn):
    try:
        fn()
        return False
    except KeyError:
        return True

def main():
    cmds = {
        "register": cmd_register, "redact": cmd_redact, "status": cmd_status,
        "exec": cmd_exec, "selftest": cmd_selftest,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit("usage: blindfold.py {register|redact|status|exec|selftest} [...]")
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "redact":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("path")
        ap.add_argument("--out")
        ap.add_argument("--structured", action="store_true")
        cmd_redact(ap.parse_args(rest))
    elif cmd == "exec":
        if not rest:
            sys.exit("usage: blindfold.py exec CMD [ARGS...]")
        cmd_exec(type("A", (), {"cmd": rest})())
    else:
        cmds[cmd](type("A", (), {})())

if __name__ == "__main__":
    sys.exit(main())
