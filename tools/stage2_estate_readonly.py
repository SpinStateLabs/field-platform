#!/usr/bin/env python3
"""stage2_estate_readonly - a READ-ONLY ``Stage2Estate`` and a thin command line for ``stage2_driver.run_stage2``.

    python tools/stage2_estate_readonly.py --records PATH --build-sha SHA --allow-already-armed
        --go-sentence-file PATH|-  [--live]  [--pg-run PATH [--allow-not-tip] [--timeout N] | --stub-snapshot FILE]
        [--services a,b,...] [--alert-estate NAME]

WHAT IT IS FOR. One thing: a native controller record (``stage_start``, ``step_done`` x2, ``stage_done``) for a Stage 2
that is ALREADY armed, through ``run_stage2(..., allow_already_armed=True)``, changing nothing on the estate. It cannot
arm, disarm or roll back anything: ``write_override``, ``delete_override`` and ``recreate_kill_switch`` raise
``ReadOnlyViolation`` unconditionally. Under ``allow_already_armed`` the driver never calls them (they are no-ops in
``Stage2Actions``); if one is ever reached, the raise is the controller's ``controller_error`` (fail closed).

WHAT IT READS. One probe per read (never cached: a counter that rose must be seen). The probe is a short script this
module writes (``probe_script``): on the host it tests that the override file exists and GETs each service ``/health``
on the loopback proxy, then prints one ``S2PROBE {json}`` line. It sends no credential and no write.

  ``override_present``  the uncommitted override file exists (a regular file)
  ``mode``              the kill-switch's own ``/health`` ``operator_mode``. NOT ``phase_g_check --expect-mode``: that
                        tool sends a probe revive that is ledgered, so it is not read-only (see its docstring)
  ``healthy``           every expected service answered ``/health`` with 200, says it is that service (``service``),
                        and reports exactly the expected ``build_sha`` (the full 40-hex sha; no prefix match)
  ``counters``          per service ``dropped_unauthenticated_records`` / ``dropped_refused_records`` as integers

A probe that cannot be run, parsed or trusted raises ``ProbeError``; a service that did not answer is left out of
``counters`` (the controller reads that as ``health_failure``). Nothing is guessed.

TRANSPORT. Injected: a callable that takes the probe script text and returns what it printed. The tests use a stub and
never open a socket. ``PgRunTransport`` hands the script to the operator's ``pg-run.py`` (the reviewed Stage 0 wrapper
and paramiko path; ``--pg-run`` names it, this repository does not ship it) as ``pg-run.py <probe.sh> --live --sha SHA``.
That wrapper saves its usual self-copy of the script under ``~/.stage0-run/`` on the host: the only write this path
makes, and not one to the compose project, a container, a key or the ledger. ``--stub-snapshot FILE`` answers every
probe from a JSON file (no network) and is refused with ``--live`` unless the records file name contains ``stub``, so a
stub run can never write ``stage_done`` into the real records.

THE COMMAND LINE REFUSES (exit 2, nothing runs) without ``--allow-already-armed``; with ``--live`` when the estate is
not armed (``stage2_not_armed``), the kill-switch is not in ``enforce`` (``stage2_not_enforce``, the half-armed case),
a service reports another build (``build_sha_mismatch``), a path is answered by another service
(``service_identity_mismatch``), ``--services`` is not all eight (``live_needs_all_services``) or ``--build-sha`` is
not the full sha (``live_needs_full_build_sha``). Without ``--live`` (the default) no probe is run at all
and the controller writes one ``plan`` row. The go sentence is Don's: it is read from a file or from stdin (``-``),
never from the argument list or the environment, and it is never printed; only its length and an 8-hex sha256 prefix
reach the records (``stage_controller``). No key or secret is read here.

Exit status: 0 completed (or the plan row written), 2 refused or a usage error, 3 the run aborted, 1 an unexpected
error (the exception type only is printed).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stage2_driver as drv  # noqa: E402
import stage_controller as sc  # noqa: E402

MARKER = "S2PROBE "
SNAPSHOT_VERSION = 1
KILL_SWITCH = "killswitch"
#: the eight services that import operator_auth, and where each one's /health is on the estate proxy
HEALTH_PATHS: dict[str, str] = {
    "registry": "/registry/health", "ledger": "/ledger/health", "delegation": "/delegation/health",
    "killswitch": "/killswitch/health", "governor": "/governor/health", "fedbroker": "/federation/health",
    "console": "/health", "lifecycle": "/lifecycle/health",
}
#: what each one's /health must say it is (``service``): a proxy route that falls through to another service's /health
#: answers 200 too, and that is not this service being healthy (tools/estate_probe.py checks the same)
SERVICE_NAMES: dict[str, str] = {
    "registry": "agent-registry", "ledger": "sealed-ledger", "delegation": "delegation-authority",
    "killswitch": "kill-switch", "governor": "spend-governor", "fedbroker": "federation-broker",
    "console": "ops-console", "lifecycle": "lifecycle-manager",
}
DEFAULT_HEALTH_BASE = "http://127.0.0.1:18080"
#: under the checkout in the host user's home (runbook: the Stage 2 override, an uncommitted file)
DEFAULT_OVERRIDE_PATH = "field-platform/integration/demo/docker-compose.require-canary.yml"
MODES = ("off", "log-only", "enforce")

REFUSE_FLAG = "allow_already_armed_required"
REFUSE_NOT_ARMED = "stage2_not_armed"
REFUSE_NOT_ENFORCE = "stage2_not_enforce"
REFUSE_BUILD = "build_sha_mismatch"
REFUSE_IDENTITY = "service_identity_mismatch"
REFUSE_SUBSET = "live_needs_all_services"
REFUSE_SHORT_SHA = "live_needs_full_build_sha"

_BASE_RE = re.compile(r"http://(127\.0\.0\.1|localhost):[0-9]{1,5}")
_PATH_RE = re.compile(r"[A-Za-z0-9._\-]+(/[A-Za-z0-9._\-]+)*")
_HEALTH_PATH_RE = re.compile(r"(/[a-z0-9\-]+)+")
_NAME_RE = re.compile(r"[a-z][a-z0-9\-]{0,31}")
_SHA40_RE = re.compile(r"[0-9a-f]{40}")

Transport = Callable[[str], str]


class ReadOnlyViolation(RuntimeError):
    """A write method of the read-only estate was called. Always raised, never a no-op."""


class ProbeError(RuntimeError):
    """The probe could not be run, or its answer cannot be trusted. The message is a fixed token."""


# ------------------------------------------------------------------ the probe script

_PROBE_BODY = r'''
import json, os, urllib.request
out = {"v": 1, "override_present": os.path.isfile(os.path.join(os.path.expanduser("~"), CFG["override_path"])),
       "services": {}}
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for name in sorted(CFG["paths"]):
    row = {"status": None}
    try:
        with opener.open(CFG["base"] + CFG["paths"][name], timeout=10) as r:
            row["status"] = r.getcode()
            h = json.loads(r.read(65536).decode("utf-8", "replace"))
        if isinstance(h, dict):
            for key in ("operator_mode", "build_sha", "service"):
                if isinstance(h.get(key), str):
                    row[key] = h[key][:64]
            for key in ("dropped_unauthenticated_records", "dropped_refused_records"):
                if isinstance(h.get(key), int) and not isinstance(h.get(key), bool):
                    row[key] = h[key]
    except Exception as exc:
        row["error"] = type(exc).__name__[:40]
    out["services"][name] = row
print("S2PROBE " + json.dumps(out, sort_keys=True))
'''


def probe_script(*, health_base: str = DEFAULT_HEALTH_BASE, override_path: str = DEFAULT_OVERRIDE_PATH,
                 paths: Mapping[str, str] | None = None) -> str:
    """The probe, as one ASCII bash script (LF). Every value that goes into it is checked against a narrow pattern, so
    nothing an operator passes can become a command. It reads: one file test and one GET per service."""
    paths = dict(HEALTH_PATHS if paths is None else paths)
    if not isinstance(health_base, str) or not _BASE_RE.fullmatch(health_base):
        raise ValueError("health base must be http://127.0.0.1:PORT (the probe runs on the host)")
    if (not isinstance(override_path, str) or not _PATH_RE.fullmatch(override_path)
            or ".." in override_path.split("/")):
        raise ValueError("override path must be a plain relative path")
    if not paths or any(not isinstance(k, str) or not _NAME_RE.fullmatch(k) or not isinstance(v, str)
                        or not _HEALTH_PATH_RE.fullmatch(v) for k, v in paths.items()):
        raise ValueError("service names and health paths must be plain")
    cfg = json.dumps({"base": health_base, "override_path": override_path, "paths": paths}, sort_keys=True)
    text = ("#!/usr/bin/env bash\n"
            "# stage2 read-only probe (tools/stage2_estate_readonly.py): one file test and GET /health per service.\n"
            "# It sends no credential and writes nothing.\n"
            "python3 - <<'S2PROBE_PY'\n"
            f"import json\nCFG = json.loads({cfg!r})"
            f"{_PROBE_BODY}"
            "S2PROBE_PY\n")
    text.encode("ascii")                             # the host output reaches a cp1252 pipe: ASCII only
    return text


# ------------------------------------------------------------------ the estate

class ReadOnlyStage2Estate:
    """``stage2_driver.Stage2Estate`` that can only read. See the module docstring."""

    def __init__(self, transport: Transport, *, services: Sequence[str] | None = None,
                 kill_switch: str = KILL_SWITCH, expected_build_sha: str | None = None,
                 health_base: str = DEFAULT_HEALTH_BASE, override_path: str = DEFAULT_OVERRIDE_PATH,
                 paths: Mapping[str, str] | None = None, service_names: Mapping[str, str] | None = None):
        paths = dict(HEALTH_PATHS if paths is None else paths)
        self.services = tuple(paths if services is None else services)
        if not self.services or any(s not in paths for s in self.services) or kill_switch not in self.services:
            raise ValueError("every service needs a health path, and the kill-switch must be one of them")
        self.transport = transport
        self.kill_switch = kill_switch
        if expected_build_sha is not None and (not isinstance(expected_build_sha, str)
                                               or not _SHA40_RE.fullmatch(expected_build_sha)):
            raise ValueError("the expected build sha must be the full 40-hex sha (it is compared for equality)")
        self.expected_build_sha = expected_build_sha
        names = dict(SERVICE_NAMES if service_names is None else service_names)
        if any(not isinstance(names.get(s), str) or not names[s] for s in self.services):
            raise ValueError("every service needs the name its /health reports")
        self.service_names = {s: names[s] for s in self.services}
        self.script = probe_script(health_base=health_base, override_path=override_path,
                                   paths={s: paths[s] for s in self.services})
        #: how many probes were run (each read method runs exactly one)
        self.probes = 0

    # -- the writes: never ------------------------------------------------------------------------------------------

    def write_override(self) -> None:
        raise ReadOnlyViolation("write_override on the read-only estate")

    def delete_override(self) -> None:
        raise ReadOnlyViolation("delete_override on the read-only estate")

    def recreate_kill_switch(self, with_override: bool) -> None:
        raise ReadOnlyViolation("recreate_kill_switch on the read-only estate")

    # -- the reads --------------------------------------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Run one probe and return its checked answer. ``ProbeError`` when there is not exactly one answer line, or
        the answer is not the expected shape: a wrong shape is never read as "absent" or "zero"."""
        self.probes += 1
        try:
            printed = self.transport(self.script)
        except ProbeError:
            raise
        except Exception:
            raise ProbeError("probe_transport_failed") from None
        if not isinstance(printed, str):
            raise ProbeError("probe_answer_not_text")
        lines = [ln[len(MARKER):] for ln in printed.splitlines() if ln.startswith(MARKER)]
        if len(lines) != 1:
            raise ProbeError("probe_answer_count")
        try:
            snap = json.loads(lines[0])
        except ValueError:
            raise ProbeError("probe_answer_not_json") from None
        if (not isinstance(snap, dict) or snap.get("v") != SNAPSHOT_VERSION
                or not isinstance(snap.get("override_present"), bool) or not isinstance(snap.get("services"), dict)
                or any(not isinstance(snap["services"].get(s), dict) for s in self.services)):
            raise ProbeError("probe_answer_shape")
        return snap

    def override_present(self) -> bool:
        return self.snapshot()["override_present"]

    def mode(self) -> str:
        row = self.snapshot()["services"][self.kill_switch]
        mode = row.get("operator_mode")
        if not self._answers(row, self.kill_switch) or mode not in MODES:
            raise ProbeError("kill_switch_mode_unreadable")
        return mode

    def healthy(self) -> bool:
        return self._healthy(self.snapshot())

    def counters(self) -> dict[str, dict[str, int]]:
        snap, out = self.snapshot(), {}
        for service in self.services:
            row = snap["services"][service]
            if not self._answers(row, service):
                continue                             # left out: the controller reads a missing service as health_failure
            out[service] = {k: row[k] for k in sc.COUNTER_KEYS
                            if isinstance(row.get(k), int) and not isinstance(row.get(k), bool)}
        return out

    # -- helpers ----------------------------------------------------------------------------------------------------

    def _answers(self, row: Mapping[str, Any], service: str) -> bool:
        """200, and the answer says it is THIS service (another service's /health behind the same path is not it)."""
        return row.get("status") == 200 and row.get("service") == self.service_names[service]

    def _identity_ok(self, snap: Mapping[str, Any]) -> bool:
        return all(snap["services"][s].get("status") != 200 or self._answers(snap["services"][s], s)
                   for s in self.services)

    def _healthy(self, snap: Mapping[str, Any]) -> bool:
        return all(self._answers(snap["services"][s], s) for s in self.services) and self._build_ok(snap)

    def _build_ok(self, snap: Mapping[str, Any]) -> bool:
        want = self.expected_build_sha
        if want is None:
            return True
        for service in self.services:
            if snap["services"][service].get("build_sha") != want:
                return False                         # equality, as estate_probe: "<sha>-dirty" is another build
        return True

    def preflight(self) -> str | None:
        """One probe, before the driver is called: the fixed refusal token, or None when the estate is armed, the
        kill-switch reads ``enforce`` and every service reports the expected build. ``ProbeError`` when it cannot tell."""
        snap = self.snapshot()
        if not snap["override_present"]:
            return REFUSE_NOT_ARMED
        row = snap["services"][self.kill_switch]
        if not self._identity_ok(snap):
            return REFUSE_IDENTITY
        if not self._answers(row, self.kill_switch) or row.get("operator_mode") != "enforce":
            return REFUSE_NOT_ENFORCE
        if not self._build_ok(snap):
            return REFUSE_BUILD
        return None


# ------------------------------------------------------------------ transports

class StubTransport:
    """Answers every probe from a JSON snapshot file. No network, no subprocess."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    def __call__(self, script: str) -> str:
        return MARKER + json.dumps(json.loads(self.path.read_text(encoding="utf-8")))


class PgRunTransport:
    """Hands the probe to ``pg-run.py`` (the Stage 0 wrapper path): ``pg-run.py <probe.sh> --live --sha SHA``. The
    argument list is fixed; nothing but the probe file, the sha and the two flags is passed."""

    def __init__(self, pg_run: str | os.PathLike, build_sha: str, *, allow_not_tip: bool = False, timeout: int = 120,
                 runner: Callable[..., Any] = subprocess.run, python: str | None = None,
                 tmpdir: str | os.PathLike | None = None):
        if not isinstance(build_sha, str) or not _SHA40_RE.fullmatch(build_sha):
            raise ValueError("pg-run needs the full 40-hex build sha")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 10 <= timeout <= 900:
            raise ValueError("timeout must be 10 to 900 seconds")
        self.pg_run = str(pg_run)
        self.build_sha = build_sha
        self.allow_not_tip = allow_not_tip
        self.timeout = timeout
        self.runner = runner
        self.python = python or sys.executable
        self.tmpdir = None if tmpdir is None else str(tmpdir)

    def command(self, script_path: str) -> list[str]:
        cmd = [self.python, self.pg_run, script_path, "--live", "--sha", self.build_sha, "--timeout", str(self.timeout)]
        if self.allow_not_tip:
            cmd.append("--allow-not-tip")
        return cmd

    def __call__(self, script: str) -> str:
        fd, name = tempfile.mkstemp(prefix="s2-readonly-probe-", suffix=".sh", dir=self.tmpdir)
        try:
            with os.fdopen(fd, "w", encoding="ascii", newline="\n") as fh:
                fh.write(script)
            done = self.runner(self.command(name), capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=self.timeout + 120, stdin=subprocess.DEVNULL)
        finally:
            try:
                os.unlink(name)
            except OSError:
                pass
        if done.returncode != 0:
            raise ProbeError("probe_transport_failed")
        return done.stdout


# ------------------------------------------------------------------ command line

class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):                        # never echo the argument list: it could hold a go sentence
        raise _UsageError()


def read_go_sentence(source: str, stdin: Any = None) -> str:
    """The go sentence from a file, or from stdin when ``source`` is ``-``. A leading byte-order mark and the
    surrounding white space are dropped (a PowerShell pipe adds both). ``Refused`` when it cannot be read; the text is
    never part of a message."""
    try:
        if source == "-":
            stream = sys.stdin if stdin is None else stdin
            raw = stream.buffer.read() if hasattr(stream, "buffer") else stream.read()
        else:
            raw = Path(source).read_bytes()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except (OSError, UnicodeError):
        raise sc.Refused("go_sentence_unreadable") from None
    return text.lstrip(chr(0xFEFF)).strip()


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="stage2_estate_readonly", allow_abbrev=False,
                description="Record an ALREADY ARMED Stage 2 natively through the controller. Read-only.")
    p.add_argument("--records", required=True, help="the controller records file")
    p.add_argument("--build-sha", dest="build_sha", required=True, help="the sha the estate runs")
    p.add_argument("--allow-already-armed", dest="allow_already_armed", action="store_true",
                   help="required: this tool only records a Stage 2 that is already armed")
    p.add_argument("--go-sentence-file", dest="go_sentence_file", required=True,
                   help="a file holding Don's go sentence, or - for stdin; never an argument, never printed")
    p.add_argument("--live", action="store_true", help="really run the controller (default: one plan row, no probe)")
    p.add_argument("--pg-run", dest="pg_run", help="path of pg-run.py (the Stage 0 wrapper path to the estate)")
    p.add_argument("--allow-not-tip", dest="allow_not_tip", action="store_true",
                   help="passed to pg-run.py: the build the estate runs is not origin/main")
    p.add_argument("--timeout", type=int, default=120, help="seconds, passed to pg-run.py (default 120)")
    p.add_argument("--stub-snapshot", dest="stub_snapshot",
                   help="answer every probe from this JSON file (no network); with --live the records file name must "
                        "contain 'stub'")
    p.add_argument("--services", help="comma list (default: the eight); --live refuses anything but all eight")
    p.add_argument("--alert-estate", dest="alert_estate", help="the estate named in the controller's alerts")
    return p


def _refuse(reason: str, records: "sc.Records | None" = None) -> int:
    if records is not None:
        try:
            records.append("refused", stage=drv.STAGE, reason=reason)
        except OSError:
            pass                                     # the refusal stands even when it cannot be recorded
    print(f"refused: {reason}")
    return 2


def main(argv: Sequence[str] | None = None, *, transport: Transport | None = None, stdin: Any = None,
         env: Mapping[str, str] | None = None) -> int:
    """``transport`` is for tests and for a caller that has its own: it replaces ``--pg-run`` / ``--stub-snapshot``.
    ``env`` is the controller's alert environment (None: the process environment; a stub snapshot always gets an empty
    one, so a stub run sends no alert)."""
    try:
        args = build_parser().parse_args(argv)
    except _UsageError:
        print("usage error: see --help (the go sentence is never an argument: use --go-sentence-file PATH or -)")
        return 2
    try:
        return _main(args, transport, stdin, env)
    except sc.Refused as exc:
        print(f"refused: {exc.reason}")
        return 2
    except Exception as exc:                         # the type only: a message could carry what a probe printed
        print(f"error: {type(exc).__name__}")
        return 1


def _main(args: argparse.Namespace, transport: Transport | None, stdin: Any, env: Mapping[str, str] | None) -> int:
    if not args.allow_already_armed:
        return _refuse(REFUSE_FLAG)
    services = tuple(s for s in (args.services or ",".join(HEALTH_PATHS)).split(",") if s)
    if any(s not in HEALTH_PATHS for s in services) or KILL_SWITCH not in services:
        return _refuse("unknown_service")
    sc.sha8_of(args.build_sha)                       # Refused("build_sha_invalid") before anything is read
    if transport is None and args.pg_run and args.stub_snapshot:
        return _refuse("one_transport_only")
    stub = transport is None and bool(args.stub_snapshot)
    records = sc.Records(args.records)
    estate = None
    if args.live:
        if set(services) != set(HEALTH_PATHS):
            return _refuse(REFUSE_SUBSET)            # stage_done says "Stage 2 is clean": all eight, or no record
        if not _SHA40_RE.fullmatch(args.build_sha):
            return _refuse(REFUSE_SHORT_SHA)         # the build is compared for equality with what /health reports
        if stub and "stub" not in Path(args.records).name.lower():
            return _refuse("stub_needs_stub_records")
        if transport is None:
            if stub:
                transport = StubTransport(args.stub_snapshot)
            elif args.pg_run:
                if not Path(args.pg_run).is_file():
                    return _refuse("pg_run_not_found")
                try:
                    transport = PgRunTransport(args.pg_run, args.build_sha, allow_not_tip=args.allow_not_tip,
                                               timeout=args.timeout)
                except ValueError:
                    return _refuse("pg_run_arguments_invalid")
            else:
                return _refuse("transport_required")
        estate = ReadOnlyStage2Estate(transport, services=services, expected_build_sha=args.build_sha)
    go_sentence = read_go_sentence(args.go_sentence_file, stdin)
    if args.live:
        try:
            reason = estate.preflight()
        except ProbeError as exc:
            return _refuse(str(exc), records)
        if reason:
            return _refuse(reason, records)
    result = drv.run_stage2(records, estate, go_sentence=go_sentence, build_sha=args.build_sha,
                            expected_services=services, live=args.live, allow_already_armed=True,
                            alert_estate=args.alert_estate, env={} if stub else env)
    if result.status == "dry-run":
        print("stage 2 plan recorded (dry run: no probe was run, nothing was changed)")
        return 0
    if result.status == "completed":
        print("stage 2 recorded: " + ", ".join(result.steps_done) + " (already armed: nothing was changed)")
        return 0
    print(f"stage 2 run {result.status}: {result.abort} (read-only: nothing was changed on the estate)")
    return 3


if __name__ == "__main__":
    sys.exit(main())
