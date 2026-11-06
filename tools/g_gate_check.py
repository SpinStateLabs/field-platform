#!/usr/bin/env python3
"""g_gate_check - walk the Phase G gate template (tasks/todo.md, "Gate template", steps 1 to 12) as a checklist.

    python tools/g_gate_check.py --state STATE.md --sha <40-hex SHA>
    python tools/g_gate_check.py --print-template [--sha <40-hex SHA>]

WHAT IT IS. A read-only check of one STATE.md gate record. It reads a single file, prints [PASS]/[FAIL] lines and an
'N/M checks passed' summary, and exits 0 only when every line of the record is present and filled. It contacts no
estate, reads no environment variable, arms nothing, installs no key and states no estate fact: every fact it reports
is a line the record already holds, and it never judges whether that line is true (a reviewer and Don do).

THE RECORD. A section of STATE.md headed ``## PHASE G GATE <sha>`` (the full 40-hex SHA, any text after it) that ends at
the next ``## `` heading. Inside it, each line is ``Label: value`` and the value must be filled (not empty, not a
``<placeholder>``, not TBD/TODO/XXX/``...``). Required labels:

  Step 1 .. Step 12   one line per step of the gate template.
  CI                  the CI status on this SHA and who confirmed it (step 4).
  Record G16 .. G18   the three records that must exist before the gate (estate-side work, recorded by Don).
  Record G25 .. G27   the go-sentence records and the D16 positive-path record, likewise.
  Armed               one line per switch armed, ``<switch> | disarm: <line>``; a switch without a disarm part fails.
                      Several lines are allowed (arming order is the order of the lines); at least one is required.
  Forward-only        which forward-only steps ran, so what is no longer reversible (step 11).
  Not-live            the keyless / not-live list (step 11).
  Don inputs          the Don inputs still outstanding (step 11); the value ``none`` is a filled value.

The gate cannot pass before the records G16 to G18 and G25 to G27 exist: each missing or placeholder record is its own
FAIL line. A record for a different SHA is not this SHA's record: the heading must carry the SHA given with --sha.

EXIT STATUS. 0 = every check passed; 1 = a check failed; 2 = refused (usage, unreadable file, SHA not 40 hex).
Standard library only; ASCII output.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

STEPS = tuple(range(1, 13))
RECORDS = ("G16", "G17", "G18", "G25", "G26", "G27")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HEADING_RE = re.compile(r"^##\s+PHASE G GATE\b(.*)$")
LINE_RE = re.compile(r"^[-*\s]*(Step\s+\d+|Record\s+G\d+|CI|Armed|Forward-only|Not-live|Don inputs)\s*:\s*(.*?)\s*$",
                     re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"(<[^<>]*>|\b(?:TBD|TODO|XXX)\b|^\.\.\.$|^\?+$)", re.IGNORECASE)
ARMED_RE = re.compile(r"^(?P<switch>[^|]*?)\s*\|\s*disarm\s*:\s*(?P<disarm>.*)$", re.IGNORECASE)

CANON = {"ci": "CI", "armed": "Armed", "forward-only": "Forward-only", "not-live": "Not-live", "don inputs": "Don inputs"}

STEP_TITLES = {
    1: "build with owner subagents",
    2: "full sweep and verify_sync.sh",
    3: "adversarial review, blockers fixed and re-verified",
    4: "push origin and gb10, SHA recorded, CI status",
    5: "GB10 pre-deploy (pins, :pre- tags, ff-only pull, build)",
    6: "GB10 deploy (outage, backup + restore-test, recreate, image IDs)",
    7: "GB10 live verification (C0, phase rows, soak)",
    8: "GB10 arming, in ARMING ORDER",
    9: "Fly pre-deploy and deploy",
    10: "Fly live verification and arming",
    11: "STATE.md record",
    12: "gate summary posted",
}

TEMPLATE = """\
## PHASE G GATE {sha}
Step 1: <owner subagents and what each built>
Step 2: <sweep result: 13 services + 2 packages; verify_sync.sh>
Step 3: <reviewer verdict on this head; blockers fixed and re-verified>
Step 4: <pushed to origin and gb10; SHA above>
Step 5: <pins; :pre- tags; ff-only pull asserted; build while old stack serves>
Step 6: <outage announced; quiesced backup + restore-test; recreate; image IDs and restart count asserted>
Step 7: <C0 and phase rows; mutations on the canary only; soak and C0 cadence>
Step 8: <switches armed in ARMING ORDER, one per recreate, C0 between each>
Step 9: <Fly pins, snapshot id, release ref; deploy; machine count, volume, image ref, restart count>
Step 10: <catalogue in-estate; Fly arming, one secret per restart, C0 between each>
Step 11: <this record>
Step 12: <gate summary posted where>
CI: <status on this SHA> confirmed by <who>
Record G16: <where the record is>
Record G17: <where the record is>
Record G18: <where the record is>
Record G25: <where the record is>
Record G26: <where the record is>
Record G27: <where the record is>
Armed: <switch> | disarm: <the one-line disarm>
Forward-only: <steps that ran and are no longer reversible, or none>
Not-live: <the keyless / not-live list>
Don inputs: <outstanding Don inputs, or none>
"""


def is_placeholder(value: str) -> bool:
    v = value.strip()
    return not v or bool(PLACEHOLDER_RE.search(v))


def find_section(text: str, sha: str):
    """Lines of the gate section whose heading carries ``sha``; None when there is no such heading."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and sha in m.group(1).lower():
            start = i
            break
    if start is None:
        return None
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return body


def parse(body: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for line in body:
        m = LINE_RE.match(line)
        if m:
            key = re.sub(r"\s+", " ", m.group(1)).lower()
            if key.startswith("step"):
                label = "Step " + key.split()[1]
            elif key.startswith("record"):
                label = "Record " + key.split()[1].upper()
            else:
                label = CANON[key]
            found.setdefault(label, []).append(m.group(2))
    return found


def check(text: str, sha: str) -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []

    def add(ok: bool, msg: str) -> None:
        results.append((ok, msg))

    body = find_section(text, sha)
    if body is None:
        add(False, f"gate record: no '## PHASE G GATE' heading carries {sha}")
        return results
    add(True, f"gate record: heading for {sha} found")
    found = parse(body)

    def one(label: str, what: str) -> None:
        vals = found.get(label, [])
        if not vals:
            add(False, f"{what}: line '{label}:' is missing")
        elif len(vals) > 1:
            add(False, f"{what}: line '{label}:' appears {len(vals)} times (one expected)")
        elif is_placeholder(vals[0]):
            add(False, f"{what}: line '{label}:' is empty or a placeholder")
        else:
            add(True, f"{what}: present")

    for n in STEPS:
        one(f"Step {n}", f"step {n} ({STEP_TITLES[n]})")
    one("CI", "step 4 CI status and who confirmed it")
    for rec in RECORDS:
        one(f"Record {rec}", f"record {rec}")

    armed = found.get("Armed", [])
    if not armed:
        add(False, "step 11 armed switches: no 'Armed:' line (one per switch, '<switch> | disarm: <line>')")
    for i, val in enumerate(armed, 1):
        m = ARMED_RE.match(val)
        if not m or is_placeholder(m.group("switch")):
            add(False, f"armed line {i}: no switch name before '| disarm:'")
        elif is_placeholder(m.group("disarm")):
            add(False, f"armed line {i}: switch '{m.group('switch').strip()}' has no disarm line")
        else:
            add(True, f"armed line {i}: '{m.group('switch').strip()}' has a disarm line")
    one("Forward-only", "step 11 forward-only steps")
    one("Not-live", "step 11 keyless / not-live list")
    one("Don inputs", "step 11 Don inputs outstanding")
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="g_gate_check", description="Walk the Phase G gate template as a checklist.")
    p.add_argument("--state", help="path of the STATE.md (or any file) holding the gate record")
    p.add_argument("--sha", help="the full 40-hex SHA the gate is for")
    p.add_argument("--print-template", action="store_true", help="print an empty record (it fails this check)")
    args = p.parse_args(argv)
    sha = (args.sha or "").lower()
    if args.print_template:
        sys.stdout.write(TEMPLATE.format(sha=sha or "<40-hex SHA>"))
        return 0
    if not args.state or not SHA_RE.match(sha):
        print("refused: --state FILE and --sha <40 lowercase hex> are both required", file=sys.stderr)
        return 2
    try:
        text = Path(args.state).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"refused: cannot read {args.state}: {type(exc).__name__}", file=sys.stderr)
        return 2
    results = check(text, sha)
    for ok, msg in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {msg}")
    passed = sum(1 for ok, _ in results if ok)
    print(f"{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
