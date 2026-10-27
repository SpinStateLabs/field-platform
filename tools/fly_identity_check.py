#!/usr/bin/env python3
"""fly_identity_check.py - Phase G C-5 in-machine check of the Fly per-process operator identities.

Runs INSIDE the Fly machine (python3, standard library only, read-only): CI's fly-image-smoke job copies it into the
container with ``docker cp`` and the Stage 4 scripts upload it with ``fly ssh sftp``. It prints NAMES, COUNTS, MODES
and booleans only, never a value of any FIELD_OPERATOR* variable and never key-file content. The last line is
``C5-RESULT: PASS`` or ``C5-RESULT: FAIL <why>`` and the exit status matches.

A process counts as a SERVICE only when its command line is ``<...>/<service> serve ...`` for one of the thirteen
services ``integration/fly/entrypoint.sh`` starts (the same rule as the Stage 0 flag checker), so this checker and the
``fly ssh console`` session, whose environment carries the app secrets, are never counted.

``--expect none``  (no identity secrets, today): no service process has FIELD_OPERATOR, FIELD_OPERATOR_KEY,
                   FIELD_OPERATOR_KEY_FILE or any FIELD_OPERATOR_KEY_<SVC> in its environment, and the key directory
                   does not exist.
``--expect four``  (the four FIELD_OPERATOR_KEY_<SVC> secrets set): each of killswitch, registry, delegation and
                   lifecycle has FIELD_OPERATOR=svc-<name> and FIELD_OPERATOR_KEY_FILE=<dir>/svc-<name>.key and
                   nothing else of that family with a value; no other service has FIELD_OPERATOR,
                   FIELD_OPERATOR_KEY_FILE or a non-empty FIELD_OPERATOR_KEY*; each key file is a regular, non-empty
                   0600 file in a 0700 directory, distinct per daemon; no process command line contains any key.
Both modes: every service is found exactly once and ``/proc/1/environ`` has no ``FIELD_OPERATOR=`` entry (the design's
"no machine-wide identity" pre-check). ``--health BASE`` also reads ``/health`` of the eight operator-block services
through the estate's single port and requires operator_identity_id / identity_present to match the expectation.

PROC_ROOT overrides /proc (tests only). Exit 0 = PASS, 1 = FAIL, 2 = usage.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.request

SERVICES = ("registry", "ledger", "delegation", "sentinel", "killswitch", "governor", "replay", "forcegw", "fedbroker",
            "console", "crosswalk", "lifecycle", "attest")
#: entrypoint launch name -> operator id (REQUIRE design v0.4 2.2.1; C-5)
DAEMONS = {"killswitch": "svc-killswitch", "registry": "svc-registry", "delegation": "svc-delegation",
           "lifecycle": "svc-lifecycle"}
SECRETS = tuple("FIELD_OPERATOR_KEY_" + d.upper() for d in DAEMONS)
IDENTITY = ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE")
#: the estate's Caddy prefix of each operator-block service ("" = the console, which owns the root)
HEALTH_PREFIX = {"registry": "registry", "ledger": "ledger", "delegation": "delegation", "killswitch": "killswitch",
                 "governor": "governor", "fedbroker": "federation", "console": "", "lifecycle": "lifecycle"}
DEFAULT_KEY_DIR = "/run/field/keys"


def service_of(argv: list[bytes]) -> str | None:
    """The service name when argv is ``<...>/<service> serve ...`` (directly or through a python interpreter)."""
    for i, a in enumerate(argv[:-1]):
        base = os.path.basename(a.decode("utf-8", "replace"))
        if base in SERVICES and argv[i + 1] == b"serve":
            return base
    return None


def _read(path: str) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def scan(proc: str, me: str) -> tuple[dict[str, list[dict[bytes, bytes]]], list[bytes], int]:
    """service -> [environ dict per matching process]; every process's raw cmdline; processes scanned."""
    found: dict[str, list[dict[bytes, bytes]]] = {}
    cmdlines: list[bytes] = []
    scanned = 0
    for d in sorted(os.listdir(proc)):
        if not d.isdigit() or d == me:
            continue
        raw_cmd = _read(os.path.join(proc, d, "cmdline"))
        raw_env = _read(os.path.join(proc, d, "environ"))
        if raw_cmd is None or raw_env is None:
            continue
        scanned += 1
        cmdlines.append(raw_cmd)
        svc = service_of([x for x in raw_cmd.split(b"\0") if x])
        if svc is None:
            continue
        env = dict(e.split(b"=", 1) for e in raw_env.split(b"\0") if b"=" in e)
        found.setdefault(svc, []).append(env)
    return found, cmdlines, scanned


def _family(env: dict[bytes, bytes]) -> dict[str, bool]:
    """FIELD_OPERATOR* identity names present in env -> has a non-blank value (the flags are not identity)."""
    names = set(IDENTITY) | set(SECRETS)
    return {k.decode(): bool(v.strip()) for k, v in env.items() if k.decode("utf-8", "replace") in names}


def check(proc: str, expect: str, key_dir: str, me: str) -> tuple[list[str], list[str]]:
    """(problems, summary lines). Never puts a value or key content into either list."""
    problems: list[str] = []
    lines: list[str] = []
    found, cmdlines, scanned = scan(proc, me)
    dup = sorted(s for s, envs in found.items() if len(envs) > 1)
    missing = [s for s in SERVICES if s not in found]
    if missing:
        problems.append("service process(es) not found by command line: " + ",".join(missing))
    if dup:
        problems.append("service(s) found more than once: " + ",".join(dup))
    pid1 = _read(os.path.join(proc, "1", "environ"))
    pid1_ids = 0 if pid1 is None else sum(1 for e in pid1.split(b"\0") if e.startswith(b"FIELD_OPERATOR="))
    if pid1 is None:
        problems.append("/proc/1/environ is not readable: the machine-wide identity count is NOT verified")
    elif pid1_ids:
        problems.append(f"/proc/1/environ has {pid1_ids} FIELD_OPERATOR= entr(y/ies): a machine-wide identity")
    with_identity = []
    for svc in SERVICES:
        for env in found.get(svc, []):
            fam = _family(env)
            valued = sorted(k for k, v in fam.items() if v)
            if expect == "none":
                if fam:
                    problems.append(f"{svc}: carries {','.join(sorted(fam))} with no identity secrets set")
                continue
            if svc in DAEMONS:
                want_id = DAEMONS[svc].encode()
                want_file = f"{key_dir}/{DAEMONS[svc]}.key".encode()
                if env.get(b"FIELD_OPERATOR", b"") != want_id:
                    problems.append(f"{svc}: FIELD_OPERATOR is not {DAEMONS[svc]}")
                if env.get(b"FIELD_OPERATOR_KEY_FILE", b"") != want_file:
                    problems.append(f"{svc}: FIELD_OPERATOR_KEY_FILE is not {want_file.decode()}")
                extra = [k for k in valued if k not in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY_FILE")]
                if extra:
                    problems.append(f"{svc}: also carries a value in {','.join(extra)}")
                if env.get(b"FIELD_OPERATOR", b"") == want_id:
                    with_identity.append(svc)
            elif valued:
                problems.append(f"{svc}: carries a value in {','.join(valued)}; only the four daemons have an identity")
    key_dir_exists = os.path.lexists(key_dir)
    files_ok = 0
    if expect == "none":
        if key_dir_exists:
            problems.append(f"{key_dir} exists with no identity secrets set")
    else:
        try:
            dst = os.lstat(key_dir)
        except OSError:
            dst = None
            problems.append(f"{key_dir} does not exist")
        if dst is not None:
            if not stat.S_ISDIR(dst.st_mode):
                problems.append(f"{key_dir} is not a directory")
            elif stat.S_IMODE(dst.st_mode) != 0o700:
                problems.append(f"{key_dir} mode is {stat.S_IMODE(dst.st_mode):04o}, want 0700")
        keys: dict[str, bytes] = {}
        for svc, op in DAEMONS.items():
            path = os.path.join(key_dir, op + ".key")
            try:
                st = os.lstat(path)
            except OSError:
                problems.append(f"{path} does not exist")
                continue
            if not stat.S_ISREG(st.st_mode):
                problems.append(f"{path} is not a regular file")
                continue
            if stat.S_IMODE(st.st_mode) != 0o600:
                problems.append(f"{path} mode is {stat.S_IMODE(st.st_mode):04o}, want 0600")
                continue
            content = (_read(path) or b"").strip()
            if not content:
                problems.append(f"{path} is empty")
                continue
            keys[svc] = content
            files_ok += 1
        if len(set(keys.values())) != len(keys):
            problems.append("two daemons share one key: every daemon must have its own")
        leaked = sum(1 for c in cmdlines for k in keys.values() if k in c)
        if leaked:
            problems.append(f"{leaked} process command line(s) contain a daemon key")
    lines.append(
        "processes_scanned=%d services_found=%d/%d daemons_with_identity=%s key_files_ok=%d/%s key_dir_exists=%s "
        "pid1_FIELD_OPERATOR_entries=%s" % (scanned, len(found), len(SERVICES), ",".join(with_identity) or "-",
                                            files_ok, 4 if expect == "four" else 0, key_dir_exists,
                                            "?" if pid1 is None else pid1_ids))
    return problems, lines


def _health(base: str, timeout: float = 5.0) -> dict[str, dict]:
    out = {}
    for svc, prefix in HEALTH_PREFIX.items():
        url = base.rstrip("/") + ("/" + prefix if prefix else "") + "/health"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 - loopback estate URL
                out[svc] = json.loads(r.read(65536).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            out[svc] = {"_error": type(exc).__name__}
    return out


def check_health(health: dict[str, dict], expect: str) -> list[str]:
    problems = []
    for svc, h in health.items():
        if "_error" in h:
            problems.append(f"{svc}: /health unreadable ({h['_error']})")
            continue
        want_id = DAEMONS.get(svc) if expect == "four" else None
        if h.get("operator_identity_id") != want_id or bool(h.get("identity_present")) != (want_id is not None):
            problems.append(f"{svc}: /health operator_identity_id={h.get('operator_identity_id')!r} "
                            f"identity_present={h.get('identity_present')!r}, want {want_id!r}/{want_id is not None}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--expect", choices=("none", "four"), required=True)
    ap.add_argument("--key-dir", default=DEFAULT_KEY_DIR)
    ap.add_argument("--health", metavar="BASE", help="e.g. http://127.0.0.1:8080 (the estate's single port)")
    a = ap.parse_args(argv)
    proc = os.environ.get("PROC_ROOT", "/proc")
    problems, lines = check(proc, a.expect, a.key_dir.rstrip("/") or "/", str(os.getpid()))
    if a.health:
        hp = check_health(_health(a.health), a.expect)
        lines.append("health_services_checked=%d health_mismatches=%d" % (len(HEALTH_PREFIX), len(hp)))
        problems += hp
    for ln in lines:
        print(ln)
    for p in problems:
        print("  problem: " + p)
    if problems:
        print("C5-RESULT: FAIL %d problem(s); first: %s" % (len(problems), problems[0]))
        return 1
    print("C5-RESULT: PASS expect=" + a.expect)
    return 0


if __name__ == "__main__":
    sys.exit(main())
