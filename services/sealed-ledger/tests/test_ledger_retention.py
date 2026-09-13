"""C2 — retention apply (archival), sidecar verify, legal hold, retention check.

Done-when (tasks/todo.md C2, C2 build spec §5.1-§5.4, §5.7, §6.1 P11-P17,
§6.2 E7, §6.3 archive/hold crash points). The rotation core is tested in
test_ledger_rotation.py; the archived READ paths there use a test stand-in,
and are exercised here again through the real ``archive_closed_segments``.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import field_core
import field_core.clients as clients
from field_core.signing import generate_keypair
from ledger_c2_support import (
    KEY_PRIV,
    KEY_PUB,
    SLOW,
    edit_line,
    fill,
    journal_records,
    listing,
    pre_c2_anchor_line,
    rotate,
    three_segments,
)
from sealed_ledger import store as store_mod
from sealed_ledger.anchors import verify_anchors, write_anchor
from sealed_ledger.api import create_app
from sealed_ledger.bundle import verify_bundle
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import (
    ArchiveRefused,
    HoldConflict,
    LedgerCorrupt,
    LedgerStore,
    LegalHoldActive,
    closed_path_for,
    journal_path_for,
    sidecar_path_for,
    verify_segment_file,
)

runner = CliRunner()
FUTURE = datetime.now(timezone.utc) + timedelta(days=3650)  # every closed segment is "old"
JOBS = max(2, min(8, os.cpu_count() or 2))
TEMPLATES = Path(field_core.__file__).resolve().parent / "templates"


def _ledger(tmp_path: Path):
    """data/ledger/events.jsonl with three segments (11 events): seg 1 = 0..3,
    seg 2 = 4..7, open seg 3 = 8..10."""
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    return data, s, p, hashes


def _apply(s: LedgerStore, data: Path, **kw):
    return s.archive_closed_segments(
        older_than_days=kw.pop("days", 1), archive_dir=kw.pop("adir", data / "ledger-archive"),
        operator=kw.pop("operator", "ops"), data_dir=data, now=kw.pop("now", FUTURE), **kw,
    )


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """No inherited service URL, secret or policy: every CLI verb here is --offline
    unless a test serves the ledger itself."""
    for name in ("FIELD_LEDGER_URL", "FIELD_SHARED_SECRET", "FIELD_LEDGER_RETENTION_DAYS",
                 "FIELD_LEDGER_ARCHIVE_DIR", "FIELD_LEDGER_CRASH_AT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    return monkeypatch


# ------------------------------------------------------------ plan Done-when


def test_archival_keeps_live_verify_ok_and_sidecar_verifies_standalone(tmp_path, env):
    data, s, p, hashes = _ledger(tmp_path)
    arch = data / "ledger-archive"
    r = _apply(s, data)
    assert r["archived_segments"] == [1, 2] and r["completed_moves"] == [] and r["pending_moves"] == []
    assert r["archive_dir"] == str(arch.resolve()) and r["retention_event_hash"]
    fresh = LedgerStore(p)
    v = fresh.verify()
    assert v.ok and v.length == 12 and v.archived_segments == 2 and v.segments == 1  # 11 + the event
    assert v.verified_events == 4
    live = fresh.events()
    assert [e.hash for e in live][:3] == hashes[8:]
    applied = [e for e in live if e.event_type == "ledger.retention.applied"]
    assert len(applied) == 1 and applied[0].hash == r["retention_event_hash"]
    assert applied[0].payload["archived_segments"] == [1, 2] and applied[0].payload["operator"] == "ops"
    health = TestClient(create_app(store=fresh)).get("/health").json()
    assert health["event_count"] == 12 and health["earliest_live_index"] == 8
    assert health["earliest_live_ts"] == live[0].ts
    assert sorted(x.name for x in p.parent.iterdir()) == [".events.jsonl.lock", "events.jsonl",
                                                          "events.segments.journal"]
    assert sorted(x.name for x in arch.iterdir()) == [
        "events-1.jsonl", "events-1.jsonl.segment.json", "events-2.jsonl", "events-2.jsonl.segment.json",
    ]
    ops = [rec for rec in journal_records(p) if rec["op"] == "archive"]
    assert [(o["n"], o["file"], o["operator"]) for o in ops] == [(1, "events-1.jsonl", "ops"),
                                                                 (2, "events-2.jsonl", "ops")]
    one = verify_segment_file(arch / "events-1.jsonl", public_key_pem=KEY_PUB)
    two = verify_segment_file(arch / "events-2.jsonl", public_key_pem=KEY_PUB)
    assert one["ok"] and one["signature_checked"] and (one["global_first"], one["global_last"]) == (0, 3)
    assert two["ok"] and (two["global_first"], two["global_last"], two["events"]) == (4, 7, 4)
    side = json.loads(sidecar_path_for(arch / "events-2.jsonl").read_text(encoding="utf-8"))
    assert side["genesis_prev_hash"] == hashes[3] and side["head_hash"] == hashes[7]
    assert side["closing_rotation_event_hash"] == hashes[8] and side["archived_by"] == "ops"
    cli = runner.invoke(cli_app, ["verify", "--path", str(arch / "events-1.jsonl")])
    assert cli.exit_code == 0, cli.output
    assert cli.stdout.splitlines()[0] == "OK — segment 1 of events.jsonl intact over 4 events (global 0..3)"
    cli = runner.invoke(cli_app, ["verify", "--path", str(arch / "events-2.jsonl"),
                                  "--pubkey", str(_pub_file(tmp_path))])
    assert cli.exit_code == 0 and "signed rotation anchor verified" in cli.stdout
    # the live store's CLI walk still says what is archived
    cli = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert cli.stdout.splitlines() == ["OK — chain intact over 12 events",
                                       "(1 segments, 2 archived; 4 events hash-verified)"]
    # mutate an archived line: the failure names the GLOBAL index
    edit_line(arch / "events-2.jsonl", 1, lambda rec: rec["payload"].update(n=99))
    bad = verify_segment_file(arch / "events-2.jsonl")
    assert not bad["ok"] and bad["reason"].startswith("segment 2: hash mismatch at index 5:")
    cli = runner.invoke(cli_app, ["verify", "--path", str(arch / "events-2.jsonl")])
    assert cli.exit_code == 1 and cli.stdout.startswith("TAMPERED — segment 2: hash mismatch at index 5:")
    assert LedgerStore(p).verify().ok  # live verify never reads the archive


def test_hold_blocks_apply_exit_4_listing_unchanged(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    arch = data / "ledger-archive"
    r = runner.invoke(cli_app, ["hold", "place", "--by", "General Counsel", "--reason", "litigation",
                                "--offline", "--path", str(p)])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["placed_by"] == "General Counsel"
    before = listing(p.parent)
    for args in (["--days", "0"], ["--days", "0", "--archive-dir", str(arch)]):
        r = runner.invoke(cli_app, ["retention", "apply", *args, "--operator", "ops",
                                    "--offline", "--path", str(p)])
        assert r.exit_code == 4, r.output
        assert r.stderr.startswith("LEGAL HOLD — legal hold in place")
    assert listing(p.parent) == before and not arch.exists()
    r = runner.invoke(cli_app, ["hold", "place", "--by", "x", "--reason", "again", "--offline", "--path", str(p)])
    assert r.exit_code == 2 and "already in place" in r.stderr
    r = runner.invoke(cli_app, ["hold", "release", "--by", "General Counsel", "--offline", "--path", str(p)])
    assert r.exit_code == 0, r.output
    released = json.loads(r.stdout)
    assert released["released_by"] == "General Counsel" and released["reason"] == "litigation"
    r = runner.invoke(cli_app, ["hold", "release", "--by", "x", "--offline", "--path", str(p)])
    assert r.exit_code == 2 and "no legal hold" in r.stderr
    types = [e.event_type for e in LedgerStore(p).events()]
    assert types.count("ledger.legal_hold.placed") == 1 and types.count("ledger.legal_hold.released") == 1
    r = runner.invoke(cli_app, ["retention", "apply", "--days", "0", "--operator", "ops",
                                "--offline", "--path", str(p)])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["archived_segments"] == [1, 2]


@pytest.mark.parametrize("by,reason", [("", "litigation"), ("   ", "litigation"), ("counsel", ""),
                                       ("counsel", "  \t ")])
def test_blank_hold_name_refused(tmp_path, env, by, reason):
    data, s, p, _ = _ledger(tmp_path)
    before = listing(p.parent)
    r = runner.invoke(cli_app, ["hold", "place", "--by", by, "--reason", reason, "--offline", "--path", str(p)])
    assert r.exit_code == 2 and "must not be blank" in r.stderr
    with pytest.raises(ValueError):
        s.place_hold(by=by, reason=reason)
    served = TestClient(create_app(store=s)).post("/hold", json={"by": by, "reason": reason})
    assert served.status_code == 422
    assert listing(p.parent) == before and not (p.parent / "legal_hold.json").exists()
    assert LedgerStore(p).verify().length == 11  # no event
    if by.strip():
        return
    s.place_hold(by="counsel", reason="litigation")
    r = runner.invoke(cli_app, ["hold", "release", "--by", by, "--offline", "--path", str(p)])
    assert r.exit_code == 2 and (p.parent / "legal_hold.json").exists()
    assert TestClient(create_app(store=s)).post("/hold/release", json={"by": by}).status_code == 422


# ----------------------------------------------------------- retention check


class StubRegistry:
    def __init__(self, agents: list[dict]):
        self.agents = agents
        self.calls = 0

    def list_agents(self, *a, **k):
        self.calls += 1
        return [dict(a) for a in self.agents]


class DeadRegistry:
    def list_agents(self, *a, **k):
        raise clients.RegistryUnreachableError("connection refused (simulated)")


def _manifest(tmp_path: Path, name: str, retention_days: int | None = None, template: str = "financial-agent") -> str:
    data = yaml.safe_load((TEMPLATES / f"field-manifest-{template}.yaml").read_text(encoding="utf-8"))
    if retention_days is not None:
        data["ledger"]["retention_days"] = retention_days
    out = tmp_path / "manifests" / f"{name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return str(out)


def _agent(agent_id: str, ref: str | None) -> dict:
    return {"agent_id": agent_id, "owner": "o", "status": "active", "manifest_ref": ref}


def test_retention_check_estate_365_vs_manifest_2555_exit_3(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "365")
    registry = StubRegistry([_agent("ssl-invoicing-agent", _manifest(tmp_path, "inv", 2555)),
                             _agent("reader", _manifest(tmp_path, "reader", 90))])
    body = TestClient(create_app(store=s, registry=registry)).get("/retention/check").json()
    assert body["status"] == "violation" and body["ok"] is False
    assert body["offending"] == [{"agent_id": "ssl-invoicing-agent", "retention_days": 2555}]
    assert body["estate_retention_days"] == 365 and body["policy_source"] == "FIELD_LEDGER_RETENTION_DAYS"
    assert body["max_manifest_retention_days"] == 2555 and body["manifests_checked"] == 2
    assert (body["segments"], body["archived_segments"], body["earliest_live_index"]) == (3, 0, 0)
    assert body["legal_hold"] is None and body["pending_moves"] == []
    env.setattr(clients, "RegistryClient", lambda *a, **k: registry)
    r = runner.invoke(cli_app, ["retention", "check", "--offline", "--path", str(p)])
    assert r.exit_code == 3, r.output
    assert json.loads(r.stdout)["offending"][0]["agent_id"] == "ssl-invoicing-agent"
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "2555")  # the compose/fly default meets the floor
    r = runner.invoke(cli_app, ["retention", "check", "--offline", "--path", str(p)])
    assert r.exit_code == 0 and json.loads(r.stdout)["status"] == "ok", r.output


def test_retention_check_agent_without_manifest_ref_skipped(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "2555")
    registry = StubRegistry([_agent("canary", _manifest(tmp_path, "canary", 2555)),
                             _agent("smoke-agent", None), _agent("legacy", "")])
    body = TestClient(create_app(store=s, registry=registry)).get("/retention/check").json()
    assert body["status"] == "ok" and body["ok"] is True
    assert body["agents_without_manifest"] == 2 and body["unresolvable"] == []
    assert body["manifests_checked"] == 1 and body["offending"] == []


def test_retention_check_unresolvable_ref_listed_exit_3(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "2555")
    garbage = tmp_path / "manifests" / "garbage.yaml"
    garbage.parent.mkdir(parents=True, exist_ok=True)
    garbage.write_text("schema_version: nope\nagent: [unclosed\n", encoding="utf-8")
    registry = StubRegistry([_agent("zeta", str(tmp_path / "manifests" / "absent.yaml")),
                             _agent("alpha", str(garbage)),
                             _agent("ok-agent", _manifest(tmp_path, "fine", 365, template="default"))])
    env.setattr(clients, "RegistryClient", lambda *a, **k: registry)
    r = runner.invoke(cli_app, ["retention", "check", "--offline", "--path", str(p)])
    assert r.exit_code == 3, r.output
    body = json.loads(r.stdout)
    assert body["status"] == "unresolvable"
    assert body["unresolvable"] == [  # sorted by agent_id: served == rendered downstream
        {"agent_id": "alpha", "manifest_ref": str(garbage), "reason": "invalid"},
        {"agent_id": "zeta", "manifest_ref": str(tmp_path / "manifests" / "absent.yaml"), "reason": "missing"},
    ]
    assert body["manifests_checked"] == 1 and body["offending"] == []


@pytest.mark.parametrize("policy,detail", [(None, "no estate policy (FIELD_LEDGER_RETENTION_DAYS unset)"),
                                           ("  ", "no estate policy (FIELD_LEDGER_RETENTION_DAYS unset)"),
                                           ("seven years", "is not an integer"), ("0", "must be >= 1")])
def test_retention_check_without_a_usable_estate_policy_exits_3(tmp_path, env, policy, detail):
    data, s, p, _ = _ledger(tmp_path)
    if policy is not None:
        env.setenv("FIELD_LEDGER_RETENTION_DAYS", policy)
    registry = StubRegistry([_agent("a", _manifest(tmp_path, "a", 2555))])
    env.setattr(clients, "RegistryClient", lambda *a, **k: registry)
    r = runner.invoke(cli_app, ["retention", "check", "--offline", "--path", str(p)])
    assert r.exit_code == 3
    body = json.loads(r.stdout)
    assert body["status"] == "no_estate_policy" and body["estate_retention_days"] is None
    assert detail in body["detail"] and body["policy_source"] is None


def test_retention_check_registry_disabled_or_down_is_unavailable_never_ok(tmp_path, env, monkeypatch):
    data, s, p, _ = _ledger(tmp_path)
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "2555")
    built: list = []
    monkeypatch.setattr(clients, "RegistryClient", lambda *a, **k: built.append(1) or StubRegistry([]))
    injected = TestClient(create_app(store=s)).get("/retention/check")  # test stacks: no registry
    assert injected.status_code == 200
    assert injected.json()["status"] == "unavailable" and injected.json()["ok"] is False
    assert "registry not configured" in injected.json()["detail"] and built == []
    down = TestClient(create_app(store=s, registry=DeadRegistry())).get("/retention/check").json()
    assert down["status"] == "unavailable" and "RegistryUnreachableError" in down["detail"]
    assert TestClient(create_app(store=s, registry=None)).get("/retention/check").json()["status"] == "unavailable"
    # the app that builds its own store builds a RegistryClient per request, from the environment
    default = TestClient(create_app())
    assert built == []
    assert default.get("/retention/check").json()["status"] == "ok" and built == [1]
    assert default.get("/retention/check").json()["status"] == "ok" and built == [1, 1]


# ------------------------------------------------------------- apply rules


def test_apply_respects_age_and_prefix_and_is_idempotent(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    r = _apply(s, data, now=datetime.now(timezone.utc))  # nothing closed more than 1 day ago
    assert (r["archived_segments"], r["completed_moves"], r["pending_moves"]) == ([], [], [])
    assert r["retention_event_hash"] is None and LedgerStore(p).verify().length == 11
    # segment 1 old enough, segment 2 not: archived segments stay a prefix
    js = store_mod.parse_journal(journal_path_for(p).read_bytes())
    closed_2 = datetime.fromisoformat(js.closed[1]["closed_at"])
    r = _apply(s, data, days=0, now=closed_2)
    assert r["archived_segments"] == [1]
    before = p.read_bytes()
    r = _apply(s, data, days=0, now=closed_2)
    assert r["archived_segments"] == [] and r["retention_event_hash"] is None
    assert p.read_bytes() == before  # no second event
    assert _apply(s, data)["archived_segments"] == [2]
    before = p.read_bytes()
    assert _apply(s, data)["archived_segments"] == [] and p.read_bytes() == before


def test_archive_dir_rules(tmp_path, env, monkeypatch):
    data, s, p, _ = _ledger(tmp_path)
    journal_before = journal_path_for(p).read_bytes()
    with pytest.raises(ArchiveRefused, match="inside the live ledger dir"):
        _apply(s, data, adir=p.parent / "archive")
    with pytest.raises(ArchiveRefused, match="inside the live ledger dir"):
        _apply(s, data, adir=p.parent)
    with pytest.raises(ArchiveRefused, match=r"outside FIELD_DATA_DIR .*--allow-external"):
        _apply(s, data, adir=tmp_path / "elsewhere")
    real_dev = store_mod._st_dev
    monkeypatch.setattr(store_mod, "_st_dev",
                        lambda path: real_dev(path) + (1 if Path(path).name == "ledger-archive" else 0))
    with pytest.raises(ArchiveRefused, match="different filesystem"):
        _apply(s, data)
    monkeypatch.setattr(store_mod, "_st_dev", real_dev)
    assert journal_path_for(p).read_bytes() == journal_before and not (tmp_path / "elsewhere").exists()
    assert sorted(x.name for x in p.parent.iterdir()) == [".events.jsonl.lock", "events-1.jsonl",
                                                          "events-2.jsonl", "events.jsonl",
                                                          "events.segments.journal"]
    with pytest.raises(ValueError):
        _apply(s, data, operator="  ")
    with pytest.raises(ValueError):
        _apply(s, data, days=-1)
    r = _apply(s, data, adir=tmp_path / "elsewhere", allow_external=True)
    assert r["archived_segments"] == [1, 2]
    assert verify_segment_file(tmp_path / "elsewhere" / "events-1.jsonl", KEY_PUB)["ok"]


def test_apply_never_archives_a_segment_that_does_not_verify(tmp_path, env):
    data, s, p, hashes = _ledger(tmp_path)
    edit_line(closed_path_for(p, 1), 2, lambda rec: rec["payload"].update(n=42))
    journal_before = journal_path_for(p).read_bytes()
    with pytest.raises(LedgerCorrupt, match=r"segment 1 does not verify against the journal; not archived "
                                            r"\(hash mismatch at index 2"):
        _apply(s, data)
    assert journal_path_for(p).read_bytes() == journal_before
    assert closed_path_for(p, 1).exists() and not (data / "ledger-archive" / "events-1.jsonl.segment.json").exists()


def test_apply_refuses_when_the_journal_disagrees_with_the_rotation_event(tmp_path, env):
    """The sidecar copies the journal entry: an edited entry (here the anchor)
    must not be archived into a sidecar that looks authoritative."""
    data, s, p, hashes = _ledger(tmp_path)
    jp = journal_path_for(p)
    lines = jp.read_bytes().split(b"\n")
    for k, line in enumerate(lines):
        if line.strip():
            rec = json.loads(line)
            if rec["op"] == "rotate-intent" and rec["n"] == 1:
                rec["anchor"]["anchored_at"] = "2020-01-01T00:00:00+00:00"
                lines[k] = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()
    jp.write_bytes(b"\n".join(lines))
    with pytest.raises(LedgerCorrupt, match=r"disagrees with the hash-chained rotation event on anchor"):
        _apply(LedgerStore(p), data)
    assert not (data / "ledger-archive" / "events-1.jsonl.segment.json").exists()
    assert [r["op"] for r in journal_records(p)].count("archive") == 0


def test_apply_never_overwrites_an_existing_archive_file_or_sidecar(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    arch = data / "ledger-archive"
    arch.mkdir(parents=True)
    (arch / "events-1.jsonl").write_bytes(b"another ledger's segment\n")
    journal_before = journal_path_for(p).read_bytes()
    with pytest.raises(ArchiveRefused, match="already exists with different content"):
        _apply(s, data)
    assert (arch / "events-1.jsonl").read_bytes() == b"another ledger's segment\n"
    (arch / "events-1.jsonl").unlink()
    sidecar_path_for(arch / "events-1.jsonl").write_text('{"format": "someone else"}\n', encoding="utf-8")
    with pytest.raises(ArchiveRefused, match="exists with different content"):
        _apply(s, data)
    assert journal_path_for(p).read_bytes() == journal_before and closed_path_for(p, 1).exists()


def test_a_rotation_between_plan_and_successor_read_replans_instead_of_refusing(tmp_path, env, monkeypatch):
    """Segment 2 is closed but its successor is the OPEN segment: a rotation that
    lands between the plan's snapshot and the read of that successor's first
    line must make apply plan again, not report a corrupt ledger."""
    data, s, p, _ = _ledger(tmp_path)
    assert _apply(s, data, days=0, now=datetime.fromisoformat(
        store_mod.parse_journal(journal_path_for(p).read_bytes()).closed[1]["closed_at"]))["archived_segments"] == [1]
    real = LedgerStore._first_event
    rotated: list = []

    def rotate_first(self, path):
        if not rotated and path == p:
            t = threading.Thread(target=lambda: rotated.append(rotate(LedgerStore(p), "concurrent")))
            t.start()
            t.join(30)
            assert rotated
        return real(self, path)

    monkeypatch.setattr(LedgerStore, "_first_event", rotate_first)
    r = _apply(s, data)
    assert rotated and r["archived_segments"] == [2, 3]
    v = LedgerStore(p).verify()
    assert v.ok and v.archived_segments == 3 and v.segments == 1


def test_a_pending_move_never_overwrites_a_different_archive_file(tmp_path, env, monkeypatch):
    """A committed archival whose file could not be moved (held open) is completed
    by the next apply — unless something else now sits at ``archived_to``: then
    both files stay as they are and the move stays pending."""
    data, s, p, _ = _ledger(tmp_path)
    arch = data / "ledger-archive"
    real = LedgerStore._move_one
    monkeypatch.setattr(LedgerStore, "_move_one", lambda self, src, dst, digest: "pending")
    r = _apply(s, data)
    assert r["archived_segments"] == [1, 2] and [m["n"] for m in r["pending_moves"]] == [1, 2]
    monkeypatch.setattr(LedgerStore, "_move_one", real)
    (arch / "events-1.jsonl").write_bytes(b"not segment 1\n")
    seg1 = closed_path_for(p, 1).read_bytes()
    r = _apply(s, data)
    assert r["completed_moves"] == [2] and [m["n"] for m in r["pending_moves"]] == [1]
    assert (arch / "events-1.jsonl").read_bytes() == b"not segment 1\n"
    assert closed_path_for(p, 1).read_bytes() == seg1 and not closed_path_for(p, 2).exists()
    assert LedgerStore(p).verify().ok


def test_hold_is_rechecked_under_the_writer_lock_before_the_journal_commit(tmp_path, env, monkeypatch):
    data, s, p, _ = _ledger(tmp_path)
    real = LedgerStore._write_sidecar
    placed: list = []

    def sidecar_then_hold(self, sidecar, side):
        real(self, sidecar, side)
        if not placed:  # another writer places a hold between the plan and the commit
            t = threading.Thread(target=lambda: placed.append(
                LedgerStore(p).place_hold(by="counsel", reason="late")))
            t.start()
            t.join(30)
            assert placed

    monkeypatch.setattr(LedgerStore, "_write_sidecar", sidecar_then_hold)
    with pytest.raises(LegalHoldActive):
        _apply(s, data)
    assert [r["op"] for r in journal_records(p)].count("archive") == 0
    assert closed_path_for(p, 1).exists() and LedgerStore(p).verify().archived_segments == 0


def test_journal_commit_precedes_the_move_and_the_move_runs_outside_the_lock(tmp_path, env, monkeypatch):
    data, s, p, _ = _ledger(tmp_path)
    seen: list = []
    real = LedgerStore._move_one

    def observe(self, src, dst, digest):
        committed = [r["n"] for r in journal_records(p) if r["op"] == "archive"]
        seen.append((src.name, committed, sidecar_path_for(dst).exists()))
        t = threading.Thread(target=lambda: LedgerStore(p).append("during-move", {}))
        t.start()
        t.join(10)  # a writer in another thread is not blocked by the archival
        seen.append(("appended", not t.is_alive()))
        return real(self, src, dst, digest)

    monkeypatch.setattr(LedgerStore, "_move_one", observe)
    assert _apply(s, data)["archived_segments"] == [1, 2]
    assert seen == [("events-1.jsonl", [1], True), ("appended", True),
                    ("events-2.jsonl", [1, 2], True), ("appended", True)]
    v = LedgerStore(p).verify()
    assert v.ok and v.length == 11 + 2 + 1


# ----------------------------------------- archived read paths, real apply


def test_journal_edit_after_real_archival_breaks_live_verify_at_next_segment_first_index(tmp_path, env):
    data, s, p, hashes = _ledger(tmp_path)
    _apply(s, data)
    jp = journal_path_for(p)
    lines = jp.read_bytes().split(b"\n")
    for k, line in enumerate(lines):
        if line.strip():
            rec = json.loads(line)
            if rec["op"] == "rotate-intent" and rec["n"] == 2:
                rec["head_hash"] = "f" * 64
                lines[k] = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()
    jp.write_bytes(b"\n".join(lines))
    v = LedgerStore(p).verify()
    assert not v.ok and v.first_break_index == 8 and v.break_segment == 3
    assert "segment 3" in v.reason


def test_anchor_inside_really_archived_segment_is_explicit_failure(tmp_path, env):
    data, s, p, hashes = _ledger(tmp_path)
    write_anchor(s, tmp_path / "live.jsonl", private_key_pem=KEY_PRIV)
    (tmp_path / "early.jsonl").write_text(pre_c2_anchor_line(3, hashes[2]), encoding="utf-8")
    _apply(s, data)
    assert verify_anchors(LedgerStore(p), tmp_path / "live.jsonl", public_key_pem=KEY_PUB).ok
    r = verify_anchors(LedgerStore(p), tmp_path / "early.jsonl", public_key_pem=KEY_PUB)
    assert not r.ok and "archived segment 1" in r.first_failure
    assert str((data / "ledger-archive" / "events-1.jsonl").resolve()) in r.first_failure


def test_export_after_real_archival_starts_at_the_earliest_live_index(tmp_path, env):
    data, s, p, hashes = _ledger(tmp_path)
    _apply(s, data)
    summary = LedgerStore(p).export(tmp_path / "exports")
    assert summary.first_index == 8 and summary.head_index == 11
    res = verify_bundle(summary.bundle_dir)
    assert res.ok and res.unfiltered and res.archived_prefix == 8


# -------------------------------------------------------------- sidecar


def test_sidecar_verify_negative_cases(tmp_path, env):
    data, s, p, hashes = _ledger(tmp_path)
    _apply(s, data)
    arch = data / "ledger-archive"
    one, two = arch / "events-1.jsonl", arch / "events-2.jsonl"
    _, stranger_pub = generate_keypair()
    assert not verify_segment_file(one, stranger_pub)["ok"]
    assert "does not verify with this public key" in verify_segment_file(one, stranger_pub)["reason"]
    assert verify_segment_file(tmp_path / "nowhere.jsonl")["reason"].startswith("no sidecar")
    # bytes that still chain (a blank line) but differ from the archived sha256
    two.write_bytes(two.read_bytes() + b"\n")
    assert verify_segment_file(two)["reason"] == "segment 2: file bytes differ from the sha256 recorded at archival"
    # dropping the first event and rewriting the sidecar to match passes WITHOUT a key for n > 1,
    # and is caught for segment 1 by its fixed start
    lines = one.read_text(encoding="utf-8").splitlines()
    one.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    side_path = sidecar_path_for(one)
    side = json.loads(side_path.read_text(encoding="utf-8"))
    side.update(start_index=1, genesis_prev_hash=hashes[0],
                sha256=hashlib.sha256(one.read_bytes()).hexdigest())
    side_path.write_text(json.dumps(side), encoding="utf-8")
    assert verify_segment_file(one)["reason"] == (
        "segment 1: segment 1 must start at global index 0 from the genesis hash")
    # a truncated tail breaks the count / the signed head
    lines = [x for x in two.read_text(encoding="utf-8").splitlines() if x.strip()]
    two.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    side_path = sidecar_path_for(two)
    side = json.loads(side_path.read_text(encoding="utf-8"))
    side.update(sha256=hashlib.sha256(two.read_bytes()).hexdigest())
    side_path.write_text(json.dumps(side), encoding="utf-8")
    assert "expected 4 events (global 4..7), found 3" in verify_segment_file(two)["reason"]
    side.update(end_index=6, head_hash=hashes[6])
    side_path.write_text(json.dumps(side), encoding="utf-8")
    assert verify_segment_file(two)["ok"]  # an unsigned sidecar is only its own claim
    signed = verify_segment_file(two, KEY_PUB)
    assert not signed["ok"] and "does not pin this segment's head" in signed["reason"]
    r = runner.invoke(cli_app, ["verify", "--path", str(two), "--anchors", str(tmp_path / "a.jsonl")])
    assert r.exit_code == 2


# ---------------------------------------------------------------- served


def test_served_hold_and_retention_routes(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "2555")
    client = TestClient(create_app(store=s, registry=StubRegistry([])))
    assert client.get("/hold").json() == {"held": False, "hold": None}
    assert client.post("/hold/release", json={"by": "x"}).status_code == 409
    assert client.post("/hold", json={"by": "counsel"}).status_code == 422
    r = client.post("/hold", json={"by": "counsel", "reason": "litigation"})
    assert r.status_code == 201 and r.json()["placed_by"] == "counsel"
    assert client.post("/hold", json={"by": "counsel", "reason": "again"}).status_code == 409
    assert client.get("/hold").json()["hold"]["reason"] == "litigation"
    assert client.get("/retention/check").json()["legal_hold"]["placed_by"] == "counsel"
    before = listing(p.parent)
    r = client.post("/retention/apply", json={"days": 0, "operator": "ops"})
    assert r.status_code == 423 and "legal hold in place" in r.json()["detail"]
    assert listing(p.parent) == before
    assert client.post("/hold/release", json={"by": "counsel"}).status_code == 200
    assert client.post("/retention/apply", json={"days": 0, "operator": " "}).status_code == 422
    assert client.post("/retention/apply", json={"days": -1, "operator": "ops"}).status_code == 422
    assert client.post("/retention/apply", json={"days": 0, "operator": "ops",
                                                 "allow_external": "true"}).status_code == 422
    r = client.post("/retention/apply", json={"days": 0, "operator": "ops",
                                              "archive_dir": str(tmp_path / "elsewhere")})
    assert r.status_code == 422 and "outside FIELD_DATA_DIR" in r.json()["detail"]
    r = client.post("/retention/apply", json={"days": 0, "operator": "ops"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["archived_segments"] == [1, 2] and body["archive_dir"] == str((data / "ledger-archive").resolve())
    check = client.get("/retention/check").json()
    assert (check["status"], check["segments"], check["archived_segments"], check["earliest_live_index"]) == (
        "ok", 1, 2, 8)
    types = [e["event_type"] for e in client.get("/events").json()]
    assert types.count("ledger.legal_hold.placed") == 1 and types.count("ledger.retention.applied") == 1
    # FIELD_LEDGER_ARCHIVE_DIR moves the default
    env.setenv("FIELD_LEDGER_ARCHIVE_DIR", str(data / "cold"))
    rotate(s)
    assert client.post("/retention/apply", json={"days": 0, "operator": "ops"}).json()["archived_segments"] == [3]
    assert (data / "cold" / "events-3.jsonl").exists()


def _serve_in_thread(app):
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    return server, thread, port


def test_cli_hold_and_retention_delegate_to_the_served_routes(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "365")
    for argv in (["hold", "place", "--by", "c", "--reason", "r"], ["hold", "release", "--by", "c"],
                 ["retention", "apply", "--days", "0", "--operator", "ops"], ["retention", "check"]):
        r = runner.invoke(cli_app, argv)
        assert r.exit_code == 2 and "set FIELD_LEDGER_URL, or pass --offline" in r.stderr, argv
    registry = StubRegistry([_agent("inv", _manifest(tmp_path, "inv", 2555))])
    outer = FastAPI()
    outer.mount("/ledger", create_app(store=LedgerStore(p), registry=registry))
    server, thread, port = _serve_in_thread(outer)
    try:
        env.setenv("FIELD_LEDGER_URL", f"http://127.0.0.1:{port}/ledger")
        r = runner.invoke(cli_app, ["hold", "place", "--by", "c", "--reason", "r", "--path", str(p)])
        assert r.exit_code == 2 and "only with --offline" in r.stderr
        r = runner.invoke(cli_app, ["hold", "place", "--by", "c", "--reason", "r"])
        assert r.exit_code == 0 and json.loads(r.stdout)["placed_by"] == "c", r.output
        r = runner.invoke(cli_app, ["hold", "place", "--by", "c", "--reason", "r"])
        assert r.exit_code == 2 and "(409)" in r.stderr
        r = runner.invoke(cli_app, ["retention", "apply", "--days", "0", "--operator", "ops"])
        assert r.exit_code == 4 and r.stderr.startswith("LEGAL HOLD —")
        r = runner.invoke(cli_app, ["retention", "check"])
        assert r.exit_code == 3 and json.loads(r.stdout)["status"] == "violation"
        assert registry.calls == 1
        assert runner.invoke(cli_app, ["hold", "release", "--by", "c"]).exit_code == 0
        r = runner.invoke(cli_app, ["retention", "apply", "--days", "0", "--operator", "ops",
                                    "--archive-dir", str(tmp_path / "elsewhere")])
        assert r.exit_code == 2 and "(422)" in r.stderr
        r = runner.invoke(cli_app, ["retention", "apply", "--days", "0", "--operator", "ops"])
        assert r.exit_code == 0, r.output
        assert json.loads(r.stdout)["archived_segments"] == [1, 2]
    finally:
        server.should_exit = True
        thread.join(30)
    v = LedgerStore(p).verify()
    assert v.ok and v.archived_segments == 2


# ------------------------------------------------------- Windows: plain handle


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing semantics (WinError 32)")
def test_windows_plain_handle_leaves_pending_move_without_duplicate(tmp_path, env):
    data, s, p, _ = _ledger(tmp_path)
    arch = data / "ledger-archive"
    fh = open(closed_path_for(p, 1), "rb")  # a plain handle: an editor, AV, an old tool
    try:
        r = _apply(s, data)
        assert r["archived_segments"] == [1, 2]
        assert r["pending_moves"] == [{"n": 1, "file": "events-1.jsonl",
                                       "archived_to": str((arch / "events-1.jsonl").resolve())}]
        assert closed_path_for(p, 1).exists() and not (arch / "events-1.jsonl").exists()  # no duplicate
        v = LedgerStore(p).verify()
        assert v.ok and v.archived_segments == 2
        assert TestClient(create_app(store=s)).get("/retention/check").json()["pending_moves"][0]["n"] == 1
    finally:
        fh.close()
    r2 = _apply(s, data)
    assert r2["completed_moves"] == [1] and r2["pending_moves"] == [] and r2["archived_segments"] == []
    assert not closed_path_for(p, 1).exists() and verify_segment_file(arch / "events-1.jsonl", KEY_PUB)["ok"]
    applied = [e for e in LedgerStore(p).events() if e.event_type == "ledger.retention.applied"]
    assert [e.payload["completed_moves"] for e in applied] == [[], [1]]


# ------------------------------------------------------------ crash points

ARCHIVE_POINTS = ["archive.sidecar_written", "archive.op_torn", "archive.committed", "archive.moved"]
HOLD_POINTS = ["hold.file_written", "hold.event_first"]

_CHILD = textwrap.dedent("""
    import sys
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from sealed_ledger.store import LedgerStore
    step, data = sys.argv[1], Path(sys.argv[2])
    s = LedgerStore(data / "ledger" / "events.jsonl")
    if step.startswith("archive."):
        s.archive_closed_segments(older_than_days=1, archive_dir=data / "ledger-archive", operator="ops",
                                  data_dir=data, now=datetime.now(timezone.utc) + timedelta(days=3650))
    elif step == "hold.file_written":
        s.place_hold(by="counsel", reason="litigation")
    else:
        s.release_hold(by="counsel")
    print("NO CRASH")
""")


@pytest.fixture(scope="module")
def crashed(tmp_path_factory):
    root = tmp_path_factory.mktemp("c2-archive-crash")
    cases = {}
    for step in ARCHIVE_POINTS + HOLD_POINTS:
        data = root / step.replace(".", "_") / "data"
        s, p, hashes = three_segments(data / "ledger")
        if step == "hold.event_first":
            s.place_hold(by="counsel", reason="litigation")
            hashes.append(LedgerStore(p).events()[-1].hash)
        cases[step] = (data, p, hashes)

    def kill(step):
        data = cases[step][0]
        env = {k: v for k, v in os.environ.items() if k != "FIELD_LEDGER_CRASH_AT"}
        env.update(PYTHONIOENCODING="utf-8", FIELD_LEDGER_CRASH_AT=step)
        return step, subprocess.run([sys.executable, "-c", _CHILD, step, str(data)], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=300, env=env)

    with ThreadPoolExecutor(JOBS) as pool:
        results = dict(pool.map(kill, cases))
    return cases, results


def _read_only_check(p: Path, hashes: list[str], data: Path) -> None:
    """Fresh-store read: ok, never shorter than acked, the live events are the
    acked suffix; the read changes nothing in the ledger or archive dirs."""
    before = listing(data)
    store = LedgerStore(p)
    v = store.verify()
    live = [e.hash for e in store.events()]
    cli = runner.invoke(cli_app, ["verify", "--path", str(p)])
    check = TestClient(create_app(store=store)).get("/retention/check").json()
    assert listing(data) == before, "a read changed a file"
    assert v.ok and v.length >= len(hashes) and cli.exit_code == 0, (v, cli.output)
    earliest = store.snapshot().earliest_live_index
    assert live[: len(hashes) - earliest] == hashes[earliest:], "SILENT: a live event is missing or moved"
    assert check["archived_segments"] == (v.archived_segments or 0)


@pytest.mark.parametrize("step", ARCHIVE_POINTS)
def test_crash_at_each_archive_step_never_silent_and_next_apply_completes(crashed, env, step):
    cases, results = crashed
    data, p, hashes = cases[step]
    child = results[step]
    assert child.returncode == 77, (child.returncode, child.stdout, child.stderr[-800:])
    arch = data / "ledger-archive"
    _read_only_check(p, hashes, data)
    complete = journal_path_for(p).read_bytes().rsplit(b"\n", 1)[0]  # a torn last record is not a record
    ops = [r for r in map(json.loads, complete.split(b"\n")) if r["op"] == "archive"]
    v = LedgerStore(p).verify()
    if step in ("archive.sidecar_written", "archive.op_torn"):
        assert ops == [] and v.archived_segments == 0 and closed_path_for(p, 1).exists()
        assert sidecar_path_for(arch / "events-1.jsonl").exists()
        if step == "archive.op_torn":
            assert not journal_path_for(p).read_bytes().endswith(b"\n")  # the torn record, ignored
    elif step == "archive.committed":
        assert [o["n"] for o in ops] == [1] and v.archived_segments == 1
        assert closed_path_for(p, 1).exists() and not (arch / "events-1.jsonl").exists()
        assert LedgerStore(p).retention_state()["pending_moves"][0]["n"] == 1
    else:
        assert [o["n"] for o in ops] == [1] and not closed_path_for(p, 1).exists()
        assert (arch / "events-1.jsonl").exists()
    out = _apply(LedgerStore(p), data, days=1)
    assert out["pending_moves"] == []
    if step == "archive.committed":
        assert out["completed_moves"] == [1] and out["archived_segments"] == [2]
    elif step == "archive.moved":
        # the documented gap: segment 1's archival is in the journal and its sidecar,
        # but no ledger.retention.applied event names it
        assert out["completed_moves"] == [] and out["archived_segments"] == [2]
    else:
        assert out["archived_segments"] == [1, 2]
    final = LedgerStore(p).verify()
    assert final.ok and final.archived_segments == 2 and final.length == len(hashes) + 1
    assert [r["n"] for r in journal_records(p) if r["op"] == "archive"] == [1, 2]
    for n in (1, 2):
        assert verify_segment_file(arch / f"events-{n}.jsonl", KEY_PUB)["ok"]
    assert not closed_path_for(p, 1).exists() and not closed_path_for(p, 2).exists()


@pytest.mark.parametrize("step", HOLD_POINTS)
def test_crash_at_each_hold_step_leaves_the_hold_in_force(crashed, env, step):
    cases, results = crashed
    data, p, hashes = cases[step]
    child = results[step]
    assert child.returncode == 77, (child.returncode, child.stdout, child.stderr[-800:])
    _read_only_check(p, hashes, data)
    store = LedgerStore(p)
    assert store.hold_status()["placed_by"] == "counsel"
    types = [e.event_type for e in store.events()]
    if step == "hold.file_written":
        assert "ledger.legal_hold.placed" not in types  # file first: the event never landed
        with pytest.raises(HoldConflict):
            store.place_hold(by="counsel", reason="retry")
    else:
        assert types.count("ledger.legal_hold.released") == 1  # event first: the file is still there
    with pytest.raises(LegalHoldActive):
        _apply(store, data)
    released = store.release_hold(by="counsel")
    assert released["placed_by"] == "counsel" and released["reason"] == "litigation"
    assert store.hold_status() is None
    assert _apply(store, data)["archived_segments"] == [1, 2]
    assert LedgerStore(p).verify().ok


# ------------------------------------------------------------------ readers


def test_readers_during_rotate_and_real_retention_apply_never_see_a_short_ok_chain(tmp_path, env):
    seconds = 8.0 if SLOW else 3.0
    data = tmp_path / "data"
    p = data / "ledger" / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 20)
    stop = time.monotonic() + seconds
    acked = [20]
    bad: list = []
    errors: list = []
    reads = [0]

    def writer():
        k = 0
        try:
            while time.monotonic() < stop:
                for _ in range(3):
                    s.append("w", {"k": k})
                    acked[0] += 1
                rotate(s)
                acked[0] += 1
                k += 1
                if k % 3 == 0:
                    r = s.archive_closed_segments(older_than_days=0, archive_dir=data / "arch",
                                                  operator="ops", data_dir=data, now=FUTURE)
                    if r["retention_event_hash"]:
                        acked[0] += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    def reader(fresh: bool):
        while time.monotonic() < stop:
            low = acked[0]
            v = (LedgerStore(p) if fresh else s).verify()
            reads[0] += 1
            if not v.ok:
                bad.append(("not ok", v.reason))
            elif v.length < low:
                bad.append(("SHORT", v.length, low))

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader, args=(f,)) for f in (True, False, True)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert errors == [] and bad == [], (errors, bad[:5])
    final = LedgerStore(p).verify()
    print(f"\nreaders during real archival: {reads[0]} reads; archived {final.archived_segments}")
    assert final.ok and final.length == acked[0] and final.archived_segments > 0


def _pub_file(tmp_path: Path) -> Path:
    f = tmp_path / "anchor-public.pem"
    f.write_text(KEY_PUB, encoding="ascii")
    return f
