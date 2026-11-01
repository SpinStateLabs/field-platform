#!/usr/bin/env python3
"""Dead-code gate (B-11): vulture at 80% confidence over every package and service source tree.

Fails on any NEW unused import, unused function argument (vulture reports it as an unused variable) or unreachable
code that is not in ALLOWLIST. At 80% confidence vulture does NOT report unused functions, classes, methods or local
variables (it reports those at 60%). A `# noqa` comment on a line suppresses vulture's finding on it, and the only
trees scanned are packages/*/src and services/*/src: tools/, plugins/, integration/ and the tests are not. Run from
the repository root:  python tools/vulture_gate.py

ALLOWLIST is exact, not a global name whitelist: one entry per (file, name) and each entry covers ONE finding, so a
second unused `msg` in the same file is still reported. An entry that no longer matches a finding is reported too
(the allowlist cannot rot). The nine entries below are parameters a framework signature forces the function to
accept (urllib's `redirect_request`, a signal handler, `HTMLParser.handle_starttag`); none is dead code.

Output names files, line numbers and identifiers only. Exit codes: 0 clean, 1 findings or stale entries,
2 vulture missing or unusable.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

MIN_CONFIDENCE = "80"

# (path relative to the root, finding name): framework-signature parameters. One entry = one finding.
ALLOWLIST: list[tuple[str, str]] = [
    ("packages/field-agent/src/field_agent/canary.py", "msg"),  # urllib HTTPRedirectHandler.redirect_request
    ("packages/field-agent/src/field_agent/canary.py", "newurl"),
    ("packages/field-agent/src/field_agent/canary.py", "signum"),  # signal handler (signum, frame)
    ("packages/field-agent/src/field_agent/canary.py", "frame"),
    ("packages/field-agent/src/field_agent/field_client.py", "msg"),  # urllib HTTPRedirectHandler.redirect_request
    ("packages/field-agent/src/field_agent/field_client.py", "newurl"),
    ("packages/field-core/src/field_core/alerts.py", "msg"),  # urllib HTTPRedirectHandler.redirect_request
    ("packages/field-core/src/field_core/alerts.py", "newurl"),
    ("services/compliance-crosswalk/src/compliance_crosswalk/regwatch.py", "attrs"),  # HTMLParser.handle_starttag
]

_FINDING = re.compile(r"^(?P<path>.+?):(?P<line>\d+): (?P<msg>.+) \((?P<conf>\d+)% confidence\)$")
_NAMED = re.compile(r"^unused \w+(?: \w+)* '(?P<name>[^']+)'$")


def source_dirs(root: Path) -> list[str]:
    """Every packages/*/src and services/*/src directory under root, as root-relative posix strings."""
    return sorted(
        p.relative_to(root).as_posix()
        for pattern in ("packages/*/src", "services/*/src")
        for p in root.glob(pattern)
        if p.is_dir()
    )


def run_vulture(root: Path, dirs: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "vulture", *dirs, "--min-confidence", MIN_CONFIDENCE],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse(stdout: str) -> list[tuple[str, int, str, str]]:
    """(path, line, name-or-message, full message) per finding."""
    out = []
    for raw in stdout.splitlines():
        m = _FINDING.match(raw.strip())
        if not m:
            continue
        named = _NAMED.match(m["msg"])
        out.append((m["path"].replace("\\", "/"), int(m["line"]), named["name"] if named else m["msg"], m["msg"]))
    return out


def gate(root: Path, allowlist: list[tuple[str, str]] = ALLOWLIST) -> tuple[int, list[str]]:
    dirs = source_dirs(root)
    if not dirs:
        return 2, ["no packages/*/src or services/*/src directory found (the gate would be blind)"]
    rc, stdout, stderr = run_vulture(root, dirs)
    if rc not in (0, 3):  # vulture: 0 nothing found, 3 findings
        return 2, [f"vulture did not run (exit {rc}); install it with the CI constraints: {stderr.strip()[:200]}"]
    allowed = Counter(allowlist)
    report: list[str] = []
    for path, line, name, msg in parse(stdout):
        if allowed[(path, name)] > 0:
            allowed[(path, name)] -= 1
            continue
        report.append(f"{path}:{line}: {msg}")
    report += [f"stale allowlist entry (no matching finding): {p} {n}" for (p, n), left in sorted(allowed.items()) for _ in range(left)]
    return (1 if report else 0), report


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    rc, report = gate(root)
    for line in report:
        print(line)
    if rc == 0:
        print(f"vulture gate: clean ({len(ALLOWLIST)} framework-signature entries allowed)")
    else:
        print(f"vulture gate: FAILED ({len(report)} item(s))")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
