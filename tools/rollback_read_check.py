#!/usr/bin/env python3
"""Rollback-read check: can the OLD release read a ledger written by the NEW release?

A rollback keeps the ledger. If the new release wrote event types the old one never wrote, the old readers must still
boot, verify, serve and replay that ledger. This tool builds a throwaway ledger with the NEW code holding every event
type added between the two commits, then runs the OLD code's readers on a copy and reports, per event type and reader:
OK, SKIPPED (the reader does not show this event, safely), REFUSED or CRASH.

It reads no estate: child processes get a scrubbed environment (no FIELD_* value from the caller), all upstreams are
in-process stubs, and everything is written under a temporary directory. See tools/rollback_read_check.md.

Exit: 0 PASS, 1 FAIL (a reader refused or crashed, or a new type has no fixture), 2 the check itself could not run.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Callable

DEFAULT_OLD = "cb7a94f8"
LEDGER_REL = Path("ledger") / "events.jsonl"
SINCE, UNTIL = "2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z"
AGENT = "rollback-check-agent"

#: First segments a ledger event type can start with. A new dotted literal under one of these with no fixture FAILS the
#: check (a false red to read, never a false green).
PREFIXES = ("kill.", "fleet.", "lifecycle.", "federation.", "spend.", "conformance.", "delegation.", "registry.", "agent.",
            "ledger.", "force.", "gateway.", "attestation.", "crosswalk.", "incident.", "operator.", "retention.", "token.",
            "approver.", "witness.", "manifest.", "bypass.", "drill.")
_DOTTED = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
_NOT_EVENT = re.compile(r"\.(py|json|yaml|yml|md|txt|html|sqlite3|jsonl|key|pem|csv|pdf|example|invalid|local|internal)$")

_CONTRACT = {"contract_id": "rollback-contract", "counterparty_org": "Example Org", "active_after": True,
             "key_present_after": False, "key_fp_after": None}
_CONTRACT_BEFORE = {"org_before": "example org", "active_before": True, "key_present_before": False, "key_fp_before": None,
                    "key_changed": False}

#: Payloads with the fields the NEW writers put in them (kill_switch/api.py, ops_console/api.py, lifecycle_manager/api.py
#: and engine.py, federation_broker/engine.py). event type -> (agent_id, payload)
FIXTURES: dict[str, tuple[str | None, dict[str, Any]]] = {
    "kill.agent.failed": (AGENT, {"operator": "rollback-check", "reason": "registry returned 502", "status_code": 502,
                                  "failure_class": "registry_failure"}),
    "kill.endpoint_failed": (AGENT, {"operator": "rollback-check", "reason": "signal_error", "outcome": "failed"}),
    "kill.drill.refused": (AGENT, {"operator": "rollback-check", "reason": "a real kill is in flight"}),
    "kill.drill.restore_skipped": (AGENT, {"operator": "rollback-check", "target_status": "active",
                                           "current_status": "killed", "reason": "superseded by kill"}),
    "fleet.halt.skipped_rows": (None, {"operator": "rollback-check", "reason": "drill", "count": 1,
                                       "skipped": [{"agent_id": AGENT, "reason": "bad row"}],
                                       "fallback_kills": [{"agent_id": AGENT, "ok": True}]}),
    "lifecycle.tick_failed": (None, {"error": "sweep upstream failed", "operator": "lifecycle-manager (scheduled)"}),
    "lifecycle.unreadable_timestamp": (AGENT, {"kind": "agent", "record_id": AGENT, "field": "attested_at",
                                               "operator": "lifecycle-manager (served)"}),
    "federation.contract.registered": (None, dict(_CONTRACT)),
    "federation.contract.replaced": (None, {**_CONTRACT, **_CONTRACT_BEFORE}),
    "federation.contract.deactivated": (None, {**_CONTRACT, **_CONTRACT_BEFORE, "active_after": False}),
    "federation.contract.refused": (None, {**_CONTRACT, "reason": "one_active_contract_per_org",
                                           "other_contract_id": "rollback-other"}),
}
#: An f-string event family found by the inventory -> the concrete types its writer produces.
FAMILIES = {"federation.contract.{}": ("federation.contract.registered", "federation.contract.replaced",
                                       "federation.contract.deactivated", "federation.contract.refused")}
#: Events the old release itself writes, around the new ones, so the chain is not made of new types only.
BASELINE: list[tuple[str, str | None, dict[str, Any]]] = [
    ("kill.agent", AGENT, {"operator": "rollback-check", "reason": "baseline"}),
    ("kill.revive", AGENT, {"operator": "rollback-check", "reason": "baseline"}),
]
READERS = ("parse", "ledger_filter", "replay", "ops_console", "status_pairing")


# ---- orchestrator ----------------------------------------------------------------------------------------------------

def extract(repo: Path, ref: str, dest: Path) -> str:
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"], capture_output=True,
                         text=True, check=True).stdout.strip()
    dest.mkdir(parents=True)
    archive = dest.parent / f"{dest.name}.tar"
    with archive.open("wb") as out:
        subprocess.run(["git", "-C", str(repo), "archive", sha, "services", "packages", "tools"], stdout=out, check=True)
    with tarfile.open(archive) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)  # noqa: S202 - our own git archive
    archive.unlink()
    return sha


def source_roots(tree: Path) -> list[Path]:
    return sorted(p for group in ("packages", "services") for p in (tree / group).glob("*/src") if p.is_dir())


def event_literals(tree: Path) -> set[str]:
    found: set[str] = set()
    for root in source_roots(tree):
        for path in root.rglob("*.py"):
            try:
                module = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(module):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if _DOTTED.match(node.value) and not _NOT_EVENT.search(node.value) and node.value.startswith(PREFIXES):
                        found.add(node.value)
                elif isinstance(node, ast.JoinedStr) and node.values and isinstance(node.values[0], ast.Constant):
                    head = node.values[0].value
                    if isinstance(head, str) and head.endswith(".") and head.startswith(PREFIXES):
                        found.add(head + "{}")
    return found


def child(python: str, role: str, tree: Path, work: Path, types: list[str]) -> subprocess.CompletedProcess:
    keep = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG") if k in os.environ}
    roots = [str(p) for p in source_roots(tree)] + [str(tree / "tools")]
    env = {**keep, "HOME": str(work), "PYTHONPATH": os.pathsep.join(roots), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
           "FIELD_DATA_DIR": str(work), "FIELD_MANIFEST_DIR": str(work / "manifests"), "NO_PROXY": "*"}
    (work / "manifests").mkdir(parents=True, exist_ok=True)
    return subprocess.run([python, str(Path(__file__).resolve()), "--role", role, "--tree", str(tree), "--work", str(work),
                           "--types", json.dumps(types)], env=env, cwd=work, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)


def tail(text: str, lines: int = 12) -> str:
    return "\n".join(text.splitlines()[-lines:])


def run(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    base = Path(tempfile.mkdtemp(prefix="rollback-read-"))
    try:
        old_sha = extract(repo, args.old, base / "old")
        new_sha = extract(repo, args.new, base / "new")
        print(f"old {old_sha}\nnew {new_sha}")
        added = event_literals(base / "new") - event_literals(base / "old")
        types: set[str] = set()
        for name in added:
            types.update(FAMILIES.get(name, (name,)))
        uncovered = sorted(t for t in types if t not in FIXTURES)
        covered = sorted(t for t in types if t in FIXTURES)
        print(f"event types added: {len(types)} ({len(covered)} with a fixture, {len(uncovered)} without)")
        if not covered:
            print("RESULT: ERROR (no added event type found: wrong commits?)")
            return 2

        write_dir = base / "write"
        write_dir.mkdir()
        done = child(args.python, "write", base / "new", write_dir, covered)
        if done.returncode != 0:
            print(f"RESULT: ERROR (the NEW code could not build the ledger)\n{tail(done.stderr)}")
            return 2
        read_dir = base / "read"
        (read_dir / LEDGER_REL.parent).mkdir(parents=True)
        shutil.copy2(write_dir / LEDGER_REL, read_dir / LEDGER_REL)
        done = child(args.python, "read", base / "old", read_dir, covered)
        report_file = read_dir / "result.json"
        if done.returncode != 0 or not report_file.is_file():
            print(f"RESULT: ERROR (the OLD readers did not finish)\n{tail(done.stderr)}")
            return 2
        report = json.loads(report_file.read_text(encoding="utf-8"))
        return summarise(report, covered, uncovered, args.json, old_sha, new_sha)
    finally:
        if args.keep:
            print(f"kept: {base}")
        else:
            shutil.rmtree(base, ignore_errors=True)


def summarise(report: dict, covered: list[str], uncovered: list[str], out: str | None, old: str, new: str) -> int:
    width = max(len(t) for t in covered)
    print(f"\n{'event type':<{width}}  " + "  ".join(f"{r:<14}" for r in READERS))
    bad: list[str] = []
    counts = {"OK": 0, "SKIPPED": 0, "REFUSED": 0, "CRASH": 0}
    for t in covered:
        cells = report["types"][t]
        print(f"{t:<{width}}  " + "  ".join(f"{cells[r]['status']:<14}" for r in READERS))
        for r in READERS:
            counts[cells[r]["status"]] += 1
            if cells[r]["status"] in ("REFUSED", "CRASH"):
                bad.append(f"{t} / {r}: {cells[r]['status']} {cells[r].get('detail', '')}")
    print("\nwhole-ledger readers")
    for name, cell in report["whole"].items():
        print(f"  {name:<24} {cell['status']} {cell.get('detail', '')}")
        counts[cell["status"]] += 1
        if cell["status"] in ("REFUSED", "CRASH"):
            bad.append(f"{name}: {cell['status']} {cell.get('detail', '')}")
    bad += [f"{t}: no fixture, not exercised" for t in uncovered]
    if out:
        Path(out).write_text(json.dumps({"old": old, "new": new, "uncovered": uncovered, "counts": counts, **report}, indent=1),
                             encoding="utf-8")
    summary = f"{len(covered)} event types, {counts['OK']} OK, {counts['SKIPPED']} skipped safely, " \
              f"{counts['REFUSED']} refused, {counts['CRASH']} crash, {len(uncovered)} without a fixture"
    if bad:
        print("\nfailures:\n  " + "\n  ".join(bad))
        print(f"\nRESULT: FAIL ({summary})")
        return 1
    print(f"\nRESULT: PASS ({summary})")
    return 0


# ---- child roles -----------------------------------------------------------------------------------------------------

def check_provenance(tree: str, names: tuple[str, ...]) -> None:
    import importlib

    root = Path(tree).resolve()
    for name in names:
        where = Path(importlib.import_module(name).__file__).resolve()
        if root not in where.parents:
            raise SystemExit(f"{name} imported from outside the extracted tree: this would test the wrong release")


def role_write(tree: str, work: Path, types: list[str]) -> int:
    check_provenance(tree, ("field_core", "sealed_ledger"))
    from sealed_ledger.store import LedgerStore

    store = LedgerStore(work / LEDGER_REL)
    for event_type, agent, payload in BASELINE:
        store.append(event_type, payload, agent)
    for event_type in types:
        agent, payload = FIXTURES[event_type]
        store.append(event_type, payload, agent)
    store.append(BASELINE[0][0], BASELINE[0][2], AGENT)
    verified = store.verify()
    if not verified.ok or verified.length != len(BASELINE) + len(types) + 1:
        raise SystemExit("the NEW store does not verify the ledger it wrote")
    return 0


def _cell(fn: Callable[[], Any]) -> dict[str, str]:
    """Run one reader. Texts are class names or fixed strings, so no event value is printed."""
    from pydantic import ValidationError

    try:
        answer = fn()
    except (ValidationError, ValueError) as exc:
        return {"status": "REFUSED", "detail": type(exc).__name__}
    except Exception as exc:  # noqa: BLE001 - the point of the check
        return {"status": "CRASH", "detail": type(exc).__name__}
    if answer is None:
        return {"status": "OK"}
    return {"status": answer[0], "detail": answer[1]}


def role_read(tree: str, work: Path, types: list[str]) -> int:
    check_provenance(tree, ("field_core", "sealed_ledger", "incident_replay", "ops_console", "estate_probe"))
    import estate_probe
    from fastapi.testclient import TestClient
    from field_core.clients import AgentNotRegisteredError
    from field_core.ledger import LedgerEvent
    from incident_replay.engine import LedgerQueryClient, ReplayEngine, ReplayRequest, _summarize, render_markdown
    from ops_console.api import create_app as ops_app
    from sealed_ledger.api import create_app as ledger_app
    from sealed_ledger.store import LedgerStore

    path = work / LEDGER_REL
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_type: dict[str, dict] = {}
    for record in records:
        by_type.setdefault(record["event_type"], record)

    # The harness must be able to see a refusal, or a PASS would mean nothing.
    try:
        LedgerEvent.model_validate({**records[0], "unknown_top_level_key": 1})
    except ValueError:
        pass
    else:
        raise SystemExit("control failed: the old model accepted an unknown top-level key")

    class Registry:
        def get_agent(self, agent_id: str) -> dict:
            raise AgentNotRegisteredError(agent_id)

    class Delegation:
        def tokens(self, agent_id: str) -> list:
            return []

    whole: dict[str, dict] = {}
    results: dict[str, dict] = {}
    with TestClient(ledger_app(store=LedgerStore(path), registry=None)) as ledger:
        whole["boot"] = {"status": "OK"}

        class OpsLedger:
            def get(self, route: str, params: dict | None = None, **_: Any) -> tuple[int, Any]:
                answer = ledger.get(route, params=params)
                return answer.status_code, answer.json()

        ops = TestClient(ops_app(ledger=OpsLedger()))
        engine = ReplayEngine(LedgerQueryClient(client=ledger, base_url="http://testserver"), Registry(), Delegation())

        def expect_200(route: str, **params: Any) -> Any:
            answer = ledger.get(route, params=params)
            if answer.status_code != 200:
                raise ValueError(f"{route} answered {answer.status_code}")
            return answer.json()

        def verify() -> tuple[str, str] | None:
            body = expect_200("/verify")
            if body.get("ok") is not True or body.get("length") != len(records):
                return "REFUSED", "the chain did not verify at the expected length"
            return None

        def unfiltered() -> tuple[str, str] | None:
            return None if len(expect_200("/events")) == len(records) else ("REFUSED", "wrong event count")

        whole["verify"] = _cell(verify)
        whole["health"] = _cell(lambda: None if expect_200("/health").get("ok") is True else ("REFUSED", "not ok"))
        whole["events_unfiltered"] = _cell(unfiltered)
        whole["retention_check"] = _cell(lambda: (expect_200("/retention/check"), None)[1])

        for event_type in types:
            record = by_type[event_type]
            agent = record.get("agent_id")

            def parse() -> None:
                LedgerEvent.model_validate(record)

            def ledger_filter() -> tuple[str, str] | None:
                rows = expect_200("/events", event_type=event_type)
                return None if len(rows) == 1 and rows[0]["hash"] == record["hash"] else ("REFUSED", "event not returned")

            def replay() -> tuple[str, str] | None:
                _summarize(record)
                if agent is None:
                    return "SKIPPED", "no agent_id: an agent replay does not show it"
                pm = engine.replay(ReplayRequest(agent_id=agent, since=SINCE, until=UNTIL))
                render_markdown(pm)
                return None if event_type in {t.event_type for t in pm.timeline} else ("REFUSED", "not in the timeline")

            def ops_console() -> tuple[str, str] | None:
                listed = ops.get("/api/events", params={"event_type": event_type})
                exported = ops.get("/api/events/export", params={"event_type": event_type, "format": "csv"})
                if listed.status_code != 200 or exported.status_code != 200:
                    return "REFUSED", f"console answered {listed.status_code}/{exported.status_code}"
                return None if event_type in exported.text else ("REFUSED", "event not in the export")

            def status_pairing() -> tuple[str, str] | None:
                # A new kill.* type must never count as the kill that explains a registry status change.
                change = {"event_type": "registry.status_changed", "agent_id": agent, "payload": {"to": "killed"}}
                shown = io.StringIO()
                with contextlib.redirect_stdout(shown):
                    estate_probe.check_status_pairing([record, change], "rollback check")
                return None if "NOT paired" in shown.getvalue() else ("REFUSED", "paired a status change")

            results[event_type] = {name: _cell(fn) for name, fn in zip(
                READERS, (parse, ledger_filter, replay, ops_console, status_pairing))}

    # The old release must also keep writing after a rollback: one more append, then a fresh process-style open.
    def append_then_verify() -> tuple[str, str] | None:
        LedgerStore(path).append(BASELINE[1][0], BASELINE[1][2], AGENT)
        verified = LedgerStore(path).verify()
        return None if verified.ok and verified.length == len(records) + 1 else ("REFUSED", "chain broke after an append")

    whole["append_after_rollback"] = _cell(append_then_verify)
    (work / "result.json").write_text(json.dumps({"types": results, "whole": whole}), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Can the old release read a ledger written by the new one?")
    parser.add_argument("--repo", default=".", help="field-platform git checkout (read only)")
    parser.add_argument("--old", default=DEFAULT_OLD, help=f"release to roll back to (default {DEFAULT_OLD})")
    parser.add_argument("--new", default="origin/main", help="release being deployed (default origin/main)")
    parser.add_argument("--python", default=sys.executable, help="interpreter with the services' dependencies")
    parser.add_argument("--json", help="also write the full result to this file")
    parser.add_argument("--keep", action="store_true", help="keep the temporary directory")
    parser.add_argument("--role", choices=("write", "read"), help=argparse.SUPPRESS)
    parser.add_argument("--tree", help=argparse.SUPPRESS)
    parser.add_argument("--work", help=argparse.SUPPRESS)
    parser.add_argument("--types", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.role:
        # Python puts this script's directory first on sys.path. Run from a checkout, that is the checkout's tools/, whose
        # estate_probe would shadow the extracted release's. Dropping it here works on every Python version (-P needs 3.11).
        here = Path(__file__).resolve().parent
        sys.path[:] = [p for p in sys.path if not p or Path(p).resolve() != here]
        role = role_write if args.role == "write" else role_read
        return role(args.tree, Path(args.work), json.loads(args.types))
    try:
        return run(args)
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"RESULT: ERROR ({type(exc).__name__})")
        return 2


if __name__ == "__main__":
    sys.exit(main())
