"""C4 — attestation: period window + signature (+ revision 2.1's canary row).

Window: ``parse_period`` / ``normalise_bound`` match the ledger's inclusive
bounds; every ledger-derived metric (each whose query hits ``/events``) carries
``since=``/``until=`` and ``basis='window'``; an all-time build carries
neither. A hand-chained ``events.jsonl`` with timestamps on both sides of the
quarter counts only in-window events and stays INTACT.

Signature: bytes = ``canonical_manifest_bytes(pack.model_dump(mode='json',
exclude={'signature'}))``; verification canonicalises the RAW parsed JSON;
mutating any field invalidates it; a wrong key is named; a blank signer is
refused; a key-load failure raises, never exits.

Served ``/pack`` honours period/since/until and is ALWAYS an unsigned draft.
Canary (rule 7) agents: one labelled row, excluded from every governance metric.

The ``_stack`` fixture is a copy of the one in test_attestation_reporter.py
(those files stay self-contained).
"""

from __future__ import annotations

import ast
import base64
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import field_core
import httpx
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import attestation_reporter.api as api_module
from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from attestation_reporter.api import create_app
from attestation_reporter.cli import app as cli_app
from attestation_reporter.engine import CANARY_AGENTS, BoardPack, PackEngine
from attestation_reporter.render import render_html
from attestation_reporter.signing import (
    InvalidSigningKey,
    PackVerificationError,
    load_signing_key,
    parse_pack_json,
    sign_pack,
    signed_bytes,
    verify_pack,
)
from attestation_reporter.window import (
    InvalidWindow,
    normalise_bound,
    parse_period,
    resolve_window,
)
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.authn import ENV_VAR
from field_core.clients import LedgerClient, RegistryClient
from field_core.ledger import GENESIS_HASH, ChainVerification, make_event
from field_core.signing import canonical_manifest_bytes, generate_keypair, key_fingerprint, sign_manifest
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
LEDGER_BASE = "http://127.0.0.1:8002"
Q3 = ("2026-07-01T00:00:00+00:00", "2026-09-30T23:59:59.999999+00:00")
runner = CliRunner()

INTEGRITY = "Ledger chain integrity"
POLICY = "Estate ledger retention policy (days)"
COUNT = "Manifests declaring more retention than the estate keeps"
RATE = "Conformance rate (ALLOW / all verdicts incl. shadow)"
ALLOW = "Conformance ALLOW verdicts"
BLOCK = "Conformance BLOCK verdicts"
DRILLS = "Kill drills completed"
REATTEST = "Re-attestation due (sweep events)"
EXPIRING_EVENTS = "Expiring authority (sweep events)"
DISTINCT_AGENTS = "Distinct agents flagged for re-attestation"
DISTINCT_TOKENS = "Distinct tokens flagged as expiring"
GATE = "Gate-verification events (canary agents, excluded from every other figure)"

#: Every metric whose query hits /events. The plan's 13 (10 event counts + the
#: derived rate + the 2 lifecycle sweep rows) plus the two de-duplicated rows
#: and the canary row C4 adds.
LEDGER_DERIVED = {
    RATE, ALLOW, BLOCK, "Conformance ESCALATE verdicts",
    "Shadow BLOCK verdicts (log-only, not enforced)",
    "Shadow ESCALATE verdicts (log-only, not enforced)",
    "Kill-switch activations", DRILLS,
    "Federation crossings allowed", "Federation crossings blocked",
    "Lifecycle orphan escalations",
    REATTEST, EXPIRING_EVENTS,
    DISTINCT_AGENTS, DISTINCT_TOKENS, GATE,
}
POINT_IN_TIME_NOTED = {
    "Agents registered", "Agents in production (active)", "Agents currently killed",
    "Open spend escalations (human queue)", INTEGRITY,
    "Authorities expiring within 30 days", "Delegation tokens issued (all time)",
    "Tokens revoked (all time)",
}


def _stack(tmp_path: Path) -> SimpleNamespace:
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t"),
    ))
    governor = TestClient(create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3")))

    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Inv",
                                   "owner": "AP Lead", "domain": "finance"})
    registry.post("/agents", json={"agent_id": "crm-agent", "name": "CRM",
                                   "owner": "RevOps", "domain": "sales"})
    registry.patch("/agents/crm-agent", json={"status": "killed"})
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller", "scope": ["draft invoices"],
        "expires_at": (NOW + timedelta(days=10)).isoformat()})
    revoked = delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller", "scope": ["read timesheets"],
        "expires_at": (NOW + timedelta(days=5)).isoformat()}).json()
    delegation.post(f"/tokens/{revoked['token_id']}/revoke")
    for event_type in ("conformance.allow", "conformance.allow", "conformance.allow",
                       "conformance.block", "conformance.escalate", "kill.agent"):
        ledger.post("/events", json={"event_type": event_type, "agent_id": "invoicing-agent",
                                     "payload": {}})
    engine = PackEngine(registry=registry, ledger=ledger, delegation=delegation, governor=governor)
    return SimpleNamespace(engine=engine, registry=registry, ledger=ledger, delegation=delegation,
                           governor=governor)


def _around_now() -> dict[str, str]:
    return {"since": (NOW - timedelta(days=1)).isoformat(), "until": (NOW + timedelta(days=1)).isoformat()}


def _by_name(pack: BoardPack) -> dict:
    return {m.name: m for m in pack.all_metrics()}


def _by_name_raw(pack: dict) -> dict:
    return {m["name"]: m for s in pack["sections"] for m in s["metrics"]}


def _q(value: str) -> str:
    return quote(value, safe=":")


def _replay(ledger: TestClient, query_part: str):
    """Send a printed source query (one `GET <base><target>` part) as-is."""
    assert query_part.startswith(f"GET {LEDGER_BASE}/"), query_part
    return ledger.get(query_part.removeprefix(f"GET {LEDGER_BASE}"))


def _chain(path: Path, rows) -> list:
    """Hand-chain (event_type, agent_id, ts, payload) rows into an events.jsonl."""
    events, prev = [], GENESIS_HASH
    for event_type, agent_id, ts, payload in rows:
        ev = make_event(event_type, payload or {}, prev_hash=prev, agent_id=agent_id, ts=ts)
        events.append(ev)
        prev = ev.hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(e.model_dump_json() + "\n" for e in events), encoding="utf-8")
    return events


@pytest.fixture(autouse=True)
def _no_secret(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


@pytest.fixture()
def keys(tmp_path):
    """Throwaway Ed25519 keys, generated in the test's temp dir."""
    private_pem, public_pem = generate_keypair()
    _, other_public = generate_keypair()
    d = tmp_path / "keys"
    d.mkdir()
    (d / "signer.pem").write_text(private_pem, encoding="ascii")
    (d / "signer.pub.pem").write_text(public_pem, encoding="ascii")
    (d / "other.pub.pem").write_text(other_public, encoding="ascii")
    return SimpleNamespace(private=private_pem, public=public_pem, other_public=other_public, dir=d)


# --- window.py ------------------------------------------------------------------------


def test_parse_period_both_spellings_give_the_utc_quarter():
    for text in ("2026-Q3", "Q3 2026", "  2026-Q3 "):
        assert tuple(d.isoformat() for d in parse_period(text)) == Q3, text
    assert tuple(d.isoformat() for d in parse_period("2026-Q4")) == (
        "2026-10-01T00:00:00+00:00", "2026-12-31T23:59:59.999999+00:00")
    assert tuple(d.isoformat() for d in parse_period("Q1 2027")) == (
        "2027-01-01T00:00:00+00:00", "2027-03-31T23:59:59.999999+00:00")
    assert tuple(d.isoformat() for d in parse_period("2028-Q2")) == (
        "2028-04-01T00:00:00+00:00", "2028-06-30T23:59:59.999999+00:00")
    assert tuple(d.isoformat() for d in parse_period("9999-Q4")) == (  # no next quarter to subtract from
        "9999-10-01T00:00:00+00:00", "9999-12-31T23:59:59.999999+00:00")


@pytest.mark.parametrize("text", [
    "Q3 2026 (demo)", "Integration demo run", "2026-Q5", "2026-Q0", "q3 2026",
    "2026Q3", "Q3-2026", "", "as of 2026-09-13",
    "0000-Q1", "Q2 0000",  # no year 0: InvalidWindow, never a bare ValueError (a served 500)
    "٢٠٢٦-Q3", "Q3 ٢٠٢٦",  # Arabic-Indic digits are not YYYY
])
def test_parse_period_is_strict(text):
    with pytest.raises(InvalidWindow):
        parse_period(text)


def test_normalise_bound_matches_the_ledgers_inclusive_bounds():
    from sealed_ledger.filters import parse_instant

    assert normalise_bound("since", "2026-07-01", end=False).isoformat() == "2026-07-01T00:00:00+00:00"
    assert normalise_bound("until", "2026-09-30", end=True).isoformat() == "2026-09-30T23:59:59.999999+00:00"
    for text in ("2026-07-01T10:00:00Z", "2026-07-01T10:00:00+00:00",
                 "2026-07-01T10:00:00", "2026-07-01T06:00:00-04:00"):
        got = normalise_bound("since", text, end=False)
        assert got.isoformat() == "2026-07-01T10:00:00+00:00", text
        assert got == parse_instant(text.replace("Z", "+00:00"))  # the instant the ledger compares
    for bad in ("yesterday", "2026-13-01", "", "2026-07-01T25:00",
                "0001-01-01T00:00:00+01:00", "9999-12-31T23:00:00-05:00"):  # no UTC instant in 0001..9999
        with pytest.raises(InvalidWindow):
            normalise_bound("since", bad, end=False)


def test_a_naive_bound_is_utc_whatever_the_host_zone():
    """On a UTC host (CI) reading a naive bound as LOCAL time is invisible, so
    a child process runs under TZ=JST-9 (UTC+9, no DST; honoured by glibc,
    macOS and the Windows CRT) and first proves that zone is in force there."""
    import os
    import subprocess
    import sys

    import attestation_reporter.window as window_module

    src = Path(window_module.__file__).resolve().parents[1]  # the package this test imported
    code = ("from datetime import datetime, timezone\n"
            "import attestation_reporter.window as w\n"
            "print(w.__file__)\n"
            "print(datetime(2026, 7, 1, 10).astimezone(timezone.utc).isoformat())\n"
            "print(w.normalise_bound('since', '2026-07-01T10:00:00', end=False).isoformat())\n"
            "print(w.normalise_bound('until', '2026-07-01T10:00:00.5', end=True).isoformat())\n")
    path = os.pathsep.join(p for p in (str(src), os.environ.get("PYTHONPATH", "")) if p)
    child = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, TZ="JST-9", PYTHONPATH=path),
                           capture_output=True, text=True, timeout=120)
    assert child.returncode == 0, child.stderr
    imported, local, since, until = child.stdout.splitlines()
    assert os.path.normcase(imported) == os.path.normcase(window_module.__file__)
    assert local == "2026-07-01T01:00:00+00:00"  # the child's local zone really is UTC+9
    assert since == "2026-07-01T10:00:00+00:00"  # naive = UTC, not local
    assert until == "2026-07-01T10:00:00.500000+00:00"


def test_period_excludes_since_until_and_neither_is_all_time():
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    for kwargs in ({"period": "2026-Q3", "since": "2026-07-01"},
                   {"period": "2026-Q3", "until": "2026-09-30"},
                   {"period": "", "since": "2026-07-01"}):
        with pytest.raises(InvalidWindow, match="mutually exclusive"):
            resolve_window(**kwargs, now=now)
    window, label = resolve_window(now=now)
    assert (window.kind, window.since, window.until, window.params()) == ("all-time", None, None, {})
    assert label == "all-time, as of 2026-09-13"
    window, label = resolve_window(period="Q3 2026", now=now)
    assert (window.kind, window.since, window.until, label) == ("quarter", *Q3, "Q3 2026")
    window, _ = resolve_window(since="2026-09-12", now=now)
    assert window.until == now.isoformat() and "until = generation time" in window.note
    window, _ = resolve_window(until="2026-09-12", now=now)
    assert window.params() == {"until": "2026-09-12T23:59:59.999999+00:00"} and "open start" in window.note
    with pytest.raises(InvalidWindow, match="after"):
        resolve_window(since="2026-09-14", until="2026-09-13", now=now)
    with pytest.raises(InvalidWindow):
        resolve_window(period="", now=now)  # a blank period is never all-time


def test_a_one_instant_window_is_accepted_and_a_blank_bound_is_refused_everywhere(tmp_path, monkeypatch):
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    window, label = resolve_window(since="2026-09-13T10:00:00Z", until="2026-09-13T10:00:00+00:00", now=now)
    instant = "2026-09-13T10:00:00+00:00"  # both bounds inclusive: since == until is one instant, not empty
    assert (window.kind, window.since, window.until, label) == ("range", instant, instant, f"{instant} .. {instant}")
    for kwargs in ({"since": ""}, {"until": ""}, {"since": "", "until": ""}, {"since": "   "}):
        with pytest.raises(InvalidWindow):  # a blank bound is never "not given" (never all-time)
            resolve_window(**kwargs, now=now)

    s = _stack(tmp_path)
    api = TestClient(create_app(engine=s.engine))
    at = NOW.isoformat()
    one = api.get("/pack", params={"since": at, "until": at})
    assert one.status_code == 200
    assert (one.json()["window"]["kind"], one.json()["window"]["since"], one.json()["window"]["until"]) == (
        "range", at, at)
    for params in ({"since": ""}, {"until": ""}, {"since": "", "until": ""}):
        for route in ("/pack", "/pack.html"):
            refused = api.get(route, params=params)
            assert refused.status_code == 422, (route, params)
            assert "sections" not in refused.text

    def never(*a, **k):
        raise AssertionError("a refused render must not query any service")

    monkeypatch.setattr(api_module, "engine_from_env", never)
    for n, argv in enumerate((["--since", ""], ["--until", ""], ["--since", "", "--until", ""])):
        out = tmp_path / "blank" / str(n)
        r = runner.invoke(cli_app, ["render", "--out", str(out), "--no-pdf", *argv])
        assert r.exit_code == 2 and r.stderr.startswith("refused: "), (argv, r.output)
        assert not out.exists(), argv


def test_out_of_range_windows_are_refused_never_a_server_error(tmp_path, monkeypatch):
    s = _stack(tmp_path)
    api = TestClient(create_app(engine=s.engine), raise_server_exceptions=False)
    bad = ({"period": "0000-Q1"}, {"period": "٢٠٢٦-Q3"}, {"since": "0001-01-01T00:00:00+01:00"},
           {"until": "9999-12-31T23:00:00-05:00"})
    for params in bad:
        for route in ("/pack", "/pack.html"):
            refused = api.get(route, params=params)
            assert refused.status_code == 422, (route, params, refused.status_code)
            assert "sections" not in refused.text

    def never(*a, **k):
        raise AssertionError("a refused render must not query any service")

    monkeypatch.setattr(api_module, "engine_from_env", never)
    for n, params in enumerate(bad):
        (flag, value), = params.items()
        out = tmp_path / "out-of-range" / str(n)
        r = runner.invoke(cli_app, ["render", "--out", str(out), "--no-pdf", f"--{flag}", value])
        assert r.exit_code == 2 and r.stderr.startswith("refused: "), (params, r.output)
        assert not out.exists(), params


# --- the window on every ledger-derived metric -------------------------------------------

EDGES = [  # (event_type, ts, inside 2026-Q3?)
    ("conformance.allow", "2026-06-30T23:59:59.999999+00:00", False),  # last microsecond of Q2
    ("conformance.allow", "2026-07-01T01:00:00+02:00", False),  # reads "July"; the instant is 06-30 23:00Z
    ("conformance.allow", "2026-07-01T00:00:00+00:00", True),  # first instant of Q3
    ("conformance.allow", "2026-08-15T12:00:00-04:00", True),
    ("conformance.block", "2026-09-30T23:59:59.999999+00:00", True),  # last microsecond of Q3
    ("conformance.block", "2026-09-30T20:30:00-04:00", False),  # reads "Sept 30"; the instant is 10-01 00:30Z
    ("kill.drill.complete", "2026-10-01T00:00:00+00:00", False),
    ("kill.drill.complete", "2026-09-01T09:00:00Z", True),
]


def test_hand_chained_ledger_counts_only_in_window_events_and_stays_intact(tmp_path):
    path = tmp_path / "ledger" / "events.jsonl"
    _chain(path, [(t, "fin-agent", ts, {}) for t, ts, _ in EDGES])
    ledger = TestClient(create_ledger_app(store=LedgerStore(path)))
    engine = PackEngine(ledger=ledger)

    pack = engine.build(period="2026-Q3")
    assert (pack.window.kind, pack.window.since, pack.window.until) == ("quarter", *Q3)
    m = _by_name(pack)
    assert (m[ALLOW].value, m[BLOCK].value, m[DRILLS].value) == (2, 1, 1)
    assert m[RATE].value == round(100 * 2 / 3, 1) and "2 / (2+1+0+0+0)" in m[RATE].note
    assert m[INTEGRITY].value == "INTACT" and "chain length 8" in m[INTEGRITY].note
    # the printed query returns exactly the in-window events
    inside = {ts for t, ts, ok in EDGES if ok and t == "conformance.allow"}
    assert {e["ts"] for e in _replay(ledger, m[ALLOW].source_query).json()} == inside

    all_time = _by_name(engine.build())
    assert (all_time[ALLOW].value, all_time[BLOCK].value, all_time[DRILLS].value) == (4, 2, 2)
    assert all_time[INTEGRITY].value == "INTACT"


def test_every_ledger_derived_metric_carries_the_window_and_all_time_has_none(tmp_path):
    s = _stack(tmp_path)
    pack = s.engine.build(**_around_now(), now=NOW)
    by_name = _by_name(pack)
    assert {m.name for m in pack.all_metrics() if "/events" in m.source_query} == LEDGER_DERIVED
    for m in pack.all_metrics():
        if m.name in LEDGER_DERIVED:
            assert m.basis == "window", m.name
            for part in m.source_query.split(" ; "):
                assert part.startswith(f"GET {LEDGER_BASE}/events?"), (m.name, part)
                assert f"since={_q(pack.window.since)}" in part and f"until={_q(pack.window.until)}" in part
                assert _replay(s.ledger, part).status_code == 200  # the printed query IS the request
        else:
            assert m.basis == "point_in_time", m.name
            assert "since=" not in m.source_query and "until=" not in m.source_query, m.name
    for name in POINT_IN_TIME_NOTED:
        assert "point-in-time" in by_name[name].note, name
    counts = LEDGER_DERIVED - {RATE, DISTINCT_AGENTS, DISTINCT_TOKENS, GATE}  # the 12 single-query event counts
    assert len(counts) == 12
    for name in counts:  # no canary staged here, so replaying the printed query IS the value
        assert len(_replay(s.ledger, by_name[name].source_query).json()) == by_name[name].value, name
    assert by_name[ALLOW].value == 3

    all_time = s.engine.build(now=NOW)
    assert (all_time.window.kind, all_time.window.since, all_time.window.until) == ("all-time", None, None)
    assert {m.name for m in all_time.all_metrics() if "/events" in m.source_query} == LEDGER_DERIVED
    for m in all_time.all_metrics():
        assert "since=" not in m.source_query and "until=" not in m.source_query, m.name


def test_ledger_down_every_ledger_metric_is_unavailable_never_a_number(tmp_path):
    class Unreachable:
        def get(self, *a, **k):
            raise httpx.ConnectError("connection refused")

    s = _stack(tmp_path)
    for ledger in (None, Unreachable()):
        s.engine.ledger = ledger
        pack = s.engine.build(**_around_now(), now=NOW)
        for m in pack.all_metrics():
            if m.name in LEDGER_DERIVED | {INTEGRITY, POLICY, COUNT}:
                assert m.status == "unavailable" and m.value is None, (ledger, m.name)
                assert m.source_query.startswith("GET ")
            if m.name in LEDGER_DERIVED:
                assert "since=" in m.source_query and "until=" in m.source_query
        assert _by_name(pack)["Agents registered"].value == 2  # other upstreams unaffected


def test_integrity_is_unavailable_not_broken_when_the_ledger_refuses_or_is_busy(tmp_path, monkeypatch):
    s = _stack(tmp_path)
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")  # every upstream now answers 401
    assert s.ledger.get("/verify").status_code == 401
    m = _by_name(s.engine.build(now=NOW))[INTEGRITY]
    assert m.status == "unavailable" and m.value is None  # a 401 is not a broken chain
    assert m.note.startswith("ledger refused /verify (HTTP 401)") and "unreachable" not in m.note
    monkeypatch.delenv(ENV_VAR)

    class Refusing:  # a ledger that answers 503 to everything
        def get(self, path, *a, **k):
            return httpx.Response(503, json={"detail": "ledger busy"})

    s.engine.ledger = Refusing()
    m = _by_name(s.engine.build(now=NOW))[INTEGRITY]
    assert m.status == "unavailable" and m.value is None
    assert "HTTP 503" in m.note and "unreachable" not in m.note
    s.engine.ledger = s.ledger

    busy = ChainVerification(ok=False, length=0, reason="ledger busy: no consistent snapshot after 90 attempts")
    monkeypatch.setattr(LedgerStore, "verify", lambda self: busy)
    m = _by_name(s.engine.build(now=NOW))[INTEGRITY]
    assert m.status == "unavailable" and m.value is None
    assert "ledger busy" in m.note and "BROKEN" not in m.note

    # only the ledger's `ledger busy:` PREFIX is busy: a real break whose reason
    # merely mentions "busy" (tamper text can say anything) is still BROKEN
    for reason in ("segment 2: link break at index 5 (busy)", "hash mismatch at index 2 — ledger busy: no"):
        broken = ChainVerification(ok=False, length=6, first_break_index=5, reason=reason)
        monkeypatch.setattr(LedgerStore, "verify", lambda self, broken=broken: broken)
        m = _by_name(s.engine.build(now=NOW))[INTEGRITY]
        assert (m.status, m.value) == ("ok", f"BROKEN — {reason}"), reason


def test_a_ledger_that_answers_verify_without_a_result_is_not_verified_never_unreachable(tmp_path):
    """C4R-9: a ledger that ANSWERS /verify without a verification result (a
    500, a 404, a 403, a 200 that is not a verification) — the pack must say
    the ledger answered and the chain was NOT verified, never 'unreachable'.
    The on-disk unparseable tamper below is now BROKEN (the ledger reports it
    as a break); the strict end-to-end check is
    test_on_disk_tampers_surface_as_broken_end_to_end_and_a_tail_deletion_is_the_limit."""
    class Answering:
        def __init__(self, status: int, body=None):
            self.status, self.body = status, body

        def get(self, path, *a, **k):
            return httpx.Response(self.status, json=self.body)

    class Unreachable:
        def get(self, *a, **k):
            raise httpx.ConnectError("connection refused")

    cases = [
        (Answering(500, {"detail": "Internal Server Error"}),
         "ledger answered HTTP 500 to /verify — chain NOT verified; investigate"),
        (Answering(404, {"detail": "Not Found"}), "ledger answered HTTP 404 to /verify — chain NOT verified; investigate"),
        (Answering(403, {"detail": "forbidden"}), "ledger refused /verify (HTTP 403) — chain not verified by this pack"),
        (Answering(200, ["not", "a", "verification"]),
         "ledger answered /verify with no verification result — chain NOT verified; investigate"),
        (Unreachable(), "ledger unreachable"),
        (None, "ledger unreachable"),
    ]
    for ledger, note in cases:
        m = _by_name(PackEngine(ledger=ledger).build(now=NOW))[INTEGRITY]
        assert (m.status, m.value, m.note) == ("unavailable", None, note), note

    # the real tamper, against a ledger that opened the file before it was edited
    store = LedgerStore(tmp_path / "ledger" / "events.jsonl")
    for i in range(5):
        store.append(event_type="conformance.allow", payload={"i": i}, agent_id="fin-agent")
    ledger = TestClient(create_ledger_app(store=store), raise_server_exceptions=False)
    clean = store.path.read_text(encoding="utf-8").splitlines(keepends=True)
    missing_key = json.dumps({k: v for k, v in json.loads(clean[2]).items() if k != "prev_hash"}) + "\n"
    for line in ("this record was overwritten\n", missing_key):
        store.path.write_text("".join(clean[:2] + [line] + clean[3:]), encoding="utf-8")
        m = _by_name(PackEngine(ledger=ledger).build(now=NOW))[INTEGRITY]
        assert "unreachable" not in (m.note or ""), line
        # BROKEN once the ledger reports a malformed record as a break; until
        # then, the ledger's answer and "NOT verified" — never a clean bill
        assert (str(m.value).startswith("BROKEN") or (
            m.status == "unavailable" and m.note.startswith("ledger answered HTTP ")
            and "chain NOT verified" in m.note)), (line, m)
    store.path.write_text("".join(clean), encoding="utf-8")
    assert _by_name(PackEngine(ledger=ledger).build(now=NOW))[INTEGRITY].value == "INTACT"


@pytest.mark.parametrize("layout", ["single-file", "rotated"])
def test_on_disk_tampers_surface_as_broken_end_to_end_and_a_tail_deletion_is_the_limit(tmp_path, layout):
    """C4R-9 residual, end to end through the real ledger app: an unparseable
    record (non-JSON, a required key deleted) and a reordered middle record are
    BROKEN with the ledger's first_break_index, never unavailable; the ledger's
    /verify answers 200. A deleted TAIL record verifies INTACT — plain verify
    cannot see it without an anchor (sealed-ledger README), pinned here. On a
    rotated ledger the closed segment is also tampered under a store opened
    AFTER the edit (a store cannot open on an unparseable OPEN segment: that
    ledger process does not start — sealed-ledger LIMITS)."""
    root = tmp_path / "ledger" / "events.jsonl"
    store = LedgerStore(root)
    for i in range(3):
        store.append(event_type="conformance.allow", payload={"i": i}, agent_id="fin-agent")
    if layout == "rotated":
        private_pem, _ = generate_keypair()
        store.rotate(private_key_pem=private_pem, operator="FIELD test", reason="C4R-9")
    for i in range(3, 8):
        store.append(event_type="conformance.allow", payload={"i": i}, agent_id="fin-agent")
    # global start of the open segment: 0 single-file, 3 after the rotation (its rotation event)
    start = 0 if layout == "single-file" else 3
    targets = [(root, start, store)]
    if layout == "rotated":
        targets.append((root.with_name("events-1.jsonl"), 0, None))  # None: open a fresh store
    k = 1  # a middle record, never the first (rotation) event of a segment
    for target, seg_start, running in targets:
        clean = target.read_text(encoding="utf-8").splitlines(keepends=True)
        missing_key = json.dumps({x: v for x, v in json.loads(clean[k]).items() if x != "prev_hash"}) + "\n"
        cases = {
            "non-json": (clean[:k] + ["this record was overwritten\n"] + clean[k + 1:],
                         "unparseable record at index"),
            "required-key-deleted": (clean[:k] + [missing_key] + clean[k + 1:], "unparseable record at index"),
            "middle-records-reordered": (clean[:k] + [clean[k + 1], clean[k]] + clean[k + 2:],
                                         "link break at index"),
        }
        for name, (lines, reason) in cases.items():
            target.write_text("".join(lines), encoding="utf-8")
            ledger = TestClient(create_ledger_app(store=running or LedgerStore(root)),
                                raise_server_exceptions=False)
            answer = ledger.get("/verify")
            assert answer.status_code == 200, (target.name, name, answer.text)
            body = answer.json()
            assert body["ok"] is False and body["first_break_index"] == seg_start + k, (target.name, name, body)
            assert reason in body["reason"], (target.name, name, body)
            m = _by_name(PackEngine(ledger=ledger).build(now=NOW))[INTEGRITY]
            assert m.status != "unavailable" and str(m.value).startswith("BROKEN — "), (target.name, name, m)
            assert reason in m.value, (target.name, name, m)
        target.write_text("".join(clean), encoding="utf-8")
    clean = root.read_text(encoding="utf-8").splitlines(keepends=True)
    root.write_text("".join(clean[:-1]), encoding="utf-8")  # the tail record deleted
    ledger = TestClient(create_ledger_app(store=LedgerStore(root)))
    assert ledger.get("/verify").json()["ok"] is True
    # the documented limit: only an anchor comparison sees a tail deletion
    assert _by_name(PackEngine(ledger=ledger).build(now=NOW))[INTEGRITY].value == "INTACT"


def test_earliest_live_note_when_the_window_starts_before_archived_history(tmp_path):
    """C3's note, from a REAL rotation + retention apply (C2)."""
    private_pem, _ = generate_keypair()
    store = LedgerStore(tmp_path / "ledger" / "events.jsonl")
    for i in range(3):
        store.append(event_type="conformance.allow", payload={"i": i}, agent_id="fin-agent")
    store.rotate(private_key_pem=private_pem, operator="FIELD test", reason="C4 earliest-live note")
    store.append(event_type="conformance.allow", payload={"i": 3}, agent_id="fin-agent")
    applied = store.archive_closed_segments(older_than_days=0, archive_dir=tmp_path / "ledger-archive",
                                            operator="FIELD test", data_dir=tmp_path)
    assert applied["archived_segments"] == [1]
    ledger = TestClient(create_ledger_app(store=store))
    health = ledger.get("/health").json()
    assert health["earliest_live_index"] == 3 and health["earliest_live_ts"]
    engine = PackEngine(ledger=ledger)
    expected = (f"window starts before the earliest live event (segments archived: 1) — the earliest "
                f"live event is global index 3 at {health['earliest_live_ts']}")

    all_time = _by_name(engine.build())
    assert expected in all_time[INTEGRITY].note and all_time[INTEGRITY].value == "INTACT"
    assert all_time[ALLOW].value == 1  # the three archived ALLOWs are not in the live ledger
    assert expected in _by_name(engine.build(**_around_now()))[INTEGRITY].note
    later = normalise_bound("since", health["earliest_live_ts"], end=False) + timedelta(microseconds=1)
    after = _by_name(engine.build(since=later.isoformat(),
                                  until=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()))
    assert "earliest live event" not in after[INTEGRITY].note
    # the boundary, both sides: a window starting EXACTLY at the earliest live
    # event misses nothing (inclusive since); one microsecond earlier does
    earliest = normalise_bound("since", health["earliest_live_ts"], end=False)
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    exact = _by_name(engine.build(since=health["earliest_live_ts"], until=tomorrow))
    assert "earliest live event" not in exact[INTEGRITY].note
    just_before = _by_name(engine.build(since=(earliest - timedelta(microseconds=1)).isoformat(), until=tomorrow))
    assert expected in just_before[INTEGRITY].note

    fresh = PackEngine(ledger=TestClient(create_ledger_app(store=LedgerStore(tmp_path / "fresh" / "e.jsonl"))))
    assert "earliest live" not in _by_name(fresh.build())[INTEGRITY].note  # nothing archived, no note


def test_lifecycle_sweep_rows_count_events_in_window_with_the_honesty_note(tmp_path):
    rows = [
        ("lifecycle.reattestation_due", "fin-agent", "2026-07-02T06:00:00+00:00", {"days_stale": 91}),
        ("lifecycle.reattestation_due", "fin-agent", "2026-07-03T06:00:00+00:00", {"days_stale": 92}),
        ("lifecycle.reattestation_due", "fin-agent", "2026-07-04T06:00:00+00:00", {"days_stale": 93}),
        ("lifecycle.reattestation_due", "crm-agent", "2026-08-01T06:00:00+00:00", {"days_stale": 95}),
        ("lifecycle.reattestation_due", "fin-agent", "2026-10-01T06:00:00+00:00", {"days_stale": 182}),
        ("lifecycle.reattestation_due", "canary-gb10", "2026-07-05T06:00:00+00:00", {"days_stale": 1}),
        ("lifecycle.expiring_authority", "fin-agent", "2026-07-02T06:00:00+00:00", {"token_id": "t-1"}),
        ("lifecycle.expiring_authority", "fin-agent", "2026-07-03T06:00:00+00:00", {"token_id": "t-1"}),
        ("lifecycle.expiring_authority", "crm-agent", "2026-07-03T06:00:00+00:00", {"token_id": "t-2"}),
        ("lifecycle.expiring_authority", "crm-agent", "2026-07-04T06:00:00+00:00", {"days_left": 19}),
        ("lifecycle.expiring_authority", "fin-agent", "2026-06-30T06:00:00+00:00", {"token_id": "t-0"}),
        ("lifecycle.expiring_authority", "canary-fly", "2026-07-06T06:00:00+00:00", {"token_id": "t-c"}),
    ]
    path = tmp_path / "ledger" / "events.jsonl"
    _chain(path, rows)
    engine = PackEngine(ledger=TestClient(create_ledger_app(store=LedgerStore(path))))
    pack = engine.build(period="2026-Q3")
    m = _by_name(pack)

    assert (m[REATTEST].value, m[REATTEST].basis) == (4, "window")
    for name in (REATTEST, EXPIRING_EVENTS):
        assert "sweep EVENTS, not distinct findings" in m[name].note and "finding-days" in m[name].note
        assert "excludes 1 gate-verification (canary) record(s)" in m[name].note
    assert m[DISTINCT_AGENTS].value == 2
    assert ("= count of distinct agent_id over the 4 lifecycle.reattestation_due event(s) in the window"
            in m[DISTINCT_AGENTS].note)
    assert m[EXPIRING_EVENTS].value == 4 and m[DISTINCT_TOKENS].value == 2
    assert "= count of distinct payload.token_id over the 4 lifecycle.expiring_authority" in m[DISTINCT_TOKENS].note
    assert "1 event(s) without payload.token_id not counted" in m[DISTINCT_TOKENS].note

    section = next(sec for sec in pack.sections if sec.title == "Expirations & re-attestation")
    assert [x.name for x in section.metrics] == [
        "Authorities expiring within 30 days", REATTEST, DISTINCT_AGENTS, EXPIRING_EVENTS, DISTINCT_TOKENS]
    delegation = next(sec for sec in pack.sections if sec.title == "Delegation")
    assert "Authorities expiring within 30 days" not in [x.name for x in delegation.metrics]

    all_time = _by_name(engine.build())
    assert (all_time[REATTEST].value, all_time[EXPIRING_EVENTS].value) == (5, 5)
    assert (all_time[DISTINCT_AGENTS].value, all_time[DISTINCT_TOKENS].value) == (2, 3)


# --- the canary row -----------------------------------------------------------------------


def test_canary_ids_are_exactly_the_estate_probes():
    probe = Path(__file__).resolve().parents[3] / "tools" / "estate_probe.py"
    sets = {}
    for node in ast.parse(probe.read_text(encoding="utf-8")).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("CANARIES", "RETIRED_CANARIES")):
            sets[node.targets[0].id] = {elt.value for elt in node.value.args[0].elts}
    assert set(sets) == {"CANARIES", "RETIRED_CANARIES"}
    assert CANARY_AGENTS == sets["CANARIES"] | sets["RETIRED_CANARIES"]


def test_canary_activity_is_one_labelled_row_and_excluded_from_every_governance_metric(tmp_path):
    s = _stack(tmp_path)
    window = _around_now()
    before = _by_name(s.engine.build(**window, now=NOW))
    assert before[GATE].value == 0

    s.registry.post("/agents", json={"agent_id": "canary-gb10", "name": "FIELD canary",
                                     "owner": "FIELD canary", "domain": "canary"})
    s.registry.post("/agents", json={"agent_id": "canary-fly", "name": "FIELD canary",
                                     "owner": "FIELD canary", "domain": "canary"})
    s.registry.patch("/agents/canary-fly", json={"status": "killed"})
    assert s.delegation.post("/tokens", json={
        "agent_id": "canary-gb10", "granted_by": "Controller", "scope": ["canary.probe"],
        "expires_at": (NOW + timedelta(days=1)).isoformat()}).status_code in (200, 201)
    assert s.governor.put("/caps/canary-gb10", json={"agent_id": "canary-gb10", "limit_cents": 100,
                                                     "escalate_at_pct": 80}).status_code == 200
    assert s.governor.post("/spend", json={"agent_id": "canary-gb10", "cents": 85}).status_code == 201
    assert [e["agent_id"] for e in s.governor.get("/escalations").json()] == ["canary-gb10"]
    staged = 0
    for agent in sorted(CANARY_AGENTS):
        for event_type in ("conformance.allow", "conformance.block", "conformance.escalate",
                           "conformance.shadow_block", "conformance.shadow_escalate", "kill.agent",
                           "kill.drill.complete", "federation.allow", "federation.block",
                           "lifecycle.orphan", "lifecycle.reattestation_due",
                           "lifecycle.expiring_authority"):
            payload = {"token_id": f"tok-{agent}"} if event_type == "lifecycle.expiring_authority" else {}
            assert s.ledger.post("/events", json={"event_type": event_type, "agent_id": agent,
                                                  "payload": payload}).status_code == 201
            staged += 1
    on_ledger = sum(len(s.ledger.get("/events", params={"agent_id": a}).json()) for a in CANARY_AGENTS)
    assert on_ledger >= staged == 48

    after = _by_name(s.engine.build(**window, now=NOW))
    for name, m in after.items():
        if name not in (GATE, INTEGRITY):
            assert (m.status, m.value) == (before[name].status, before[name].value), name
    gate = after[GATE]
    assert (gate.value, gate.unit, gate.basis) == (on_ledger, "events", "window")
    for agent in CANARY_AGENTS:
        assert f"GET {LEDGER_BASE}/events?agent_id={agent}&since=" in gate.source_query
        assert agent in gate.note
    assert "excluded from every governance metric" in gate.note
    assert "excludes 4 gate-verification (canary) record(s)" in after[ALLOW].note
    assert "excludes 1 gate-verification" in after["Agents in production (active)"].note
    assert "excludes 1 gate-verification" in after["Agents currently killed"].note
    assert "excludes 1 gate-verification" in after["Delegation tokens issued (all time)"].note
    assert "excludes 1 gate-verification" in after["Open spend escalations (human queue)"].note

    # EXACT ids, never a prefix: agents merely named like a canary are governance
    for agent in ("canary-gb10-shadow", "canary"):
        s.ledger.post("/events", json={"event_type": "conformance.allow", "agent_id": agent, "payload": {}})
    later = _by_name(s.engine.build(**window, now=NOW))
    assert later[ALLOW].value == after[ALLOW].value + 2 and later[GATE].value == gate.value


def test_canary_retention_findings_are_excluded_from_the_count(tmp_path, monkeypatch):
    class StubRegistry:
        def __init__(self, agents):
            self.agents = agents

        def list_agents(self, *a, **k):
            return [dict(x) for x in self.agents]

    template = Path(field_core.__file__).resolve().parent / "templates" / "field-manifest-client-facing-agent.yaml"
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    for name in ("crm", "canary"):
        (manifests / f"{name}.yaml").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("FIELD_LEDGER_RETENTION_DAYS", "365")
    registry = StubRegistry([
        {"agent_id": "crm", "manifest_ref": str(manifests / "crm.yaml")},  # 730 d > 365
        {"agent_id": "canary-gb10", "manifest_ref": str(manifests / "canary.yaml")},  # 730 d, a canary
        {"agent_id": "canary-fly", "manifest_ref": str(manifests / "gone.yaml")},  # unresolvable, a canary
    ])
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl"), registry=registry))
    count = _by_name(PackEngine(ledger=ledger).build())[COUNT]
    assert count.value == 1
    assert count.note == "offending: crm (730 d); excludes 2 gate-verification (canary) finding(s)"


# --- the signature ------------------------------------------------------------------------


def _leaves(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, path + (i,))
    else:
        yield path


def _mutated(raw: dict, path: tuple) -> dict:
    out = copy.deepcopy(raw)
    parent = out
    for key in path[:-1]:
        parent = parent[key]
    old = parent[path[-1]]
    if isinstance(old, bool):
        new = not old
    elif isinstance(old, (int, float)):
        new = old + 1
    elif old is None:
        new = "tampered"
    else:
        new = old + " (edited)"
    parent[path[-1]] = new
    return out


def test_every_field_of_a_signed_pack_is_inside_the_signature(tmp_path, keys):
    s = _stack(tmp_path)
    pack = sign_pack(s.engine.build(**_around_now(), now=NOW), "Don Hagell", keys.private)
    raw = json.loads(pack.model_dump_json(indent=2))  # exactly what `attest render` writes
    assert verify_pack(raw, keys.public)["signer"] == "Don Hagell"
    assert verify_pack(json.loads(json.dumps(raw, sort_keys=True)), keys.public)  # formatting is not content

    leaves = [p for p in _leaves(raw) if p != ("signature",)]
    named = [("signer",), ("signed_at",), ("period",), ("window", "since"), ("generated_at",)] + [
        ("sections", 2, "metrics", 1, field)
        for field in ("name", "value", "unit", "source_query", "status", "note", "basis")]
    assert set(named) <= set(leaves) and len(leaves) > 150
    for path in leaves:
        with pytest.raises(PackVerificationError) as exc:
            verify_pack(_mutated(raw, path), keys.public)
        if path == ("key_fingerprint",):
            assert "wrong key" in str(exc.value)
        elif path == ("signed",):
            assert "nothing to verify" in str(exc.value)
        else:
            assert "signature INVALID" in str(exc.value), path

    # the verifier reads the RAW JSON: an added or removed key fails, although a
    # re-validated model would silently drop the added one
    added = copy.deepcopy(raw)
    added["approved_by_board"] = True
    removed = copy.deepcopy(raw)
    del removed["method"]
    extra_in_metric = copy.deepcopy(raw)
    extra_in_metric["sections"][2]["metrics"][1]["adjusted"] = 0
    for edited in (added, removed, extra_in_metric):
        with pytest.raises(PackVerificationError, match="signature INVALID"):
            verify_pack(edited, keys.public)
    revalidated = BoardPack.model_validate(added).model_dump(mode="json")
    assert revalidated == BoardPack.model_validate(raw).model_dump(mode="json")


def test_signature_is_over_the_dump_without_the_signature_key(tmp_path, keys):
    s = _stack(tmp_path)
    pack = sign_pack(s.engine.build(now=NOW), "Don Hagell", keys.private)
    public = serialization.load_pem_public_key(keys.public.encode("ascii"))
    sig = base64.b64decode(pack.signature)
    exact = canonical_manifest_bytes(pack.model_dump(mode="json", exclude={"signature"}))
    assert signed_bytes(pack) == exact and b'"signature"' not in exact
    public.verify(sig, exact)  # raises if the signature is over anything else
    with_none = pack.model_dump(mode="json")
    with_none["signature"] = None
    with pytest.raises(InvalidSignature):
        public.verify(sig, canonical_manifest_bytes(with_none))
    assert pack.key_fingerprint == key_fingerprint(keys.public)


def test_wrong_key_is_named_and_a_blank_signer_is_refused(tmp_path, keys):
    s = _stack(tmp_path)
    unsigned = s.engine.build(now=NOW)
    for blank in ("", "   ", "\t\n", None):
        with pytest.raises(ValueError, match="blank refused"):
            sign_pack(unsigned, blank, keys.private)
    signed = sign_pack(unsigned, "Don Hagell", keys.private)
    with pytest.raises(ValueError, match="already signed"):
        sign_pack(signed, "Someone Else", keys.private)

    raw = json.loads(signed.model_dump_json())
    with pytest.raises(PackVerificationError, match="wrong key") as exc:
        verify_pack(raw, keys.other_public)
    assert signed.key_fingerprint[:16] in str(exc.value)
    assert key_fingerprint(keys.other_public)[:16] in str(exc.value)
    with pytest.raises(PackVerificationError, match="names no signer"):
        verify_pack({**raw, "signer": "  "}, keys.public)

    unsigned_raw = json.loads(unsigned.model_dump_json())
    assert (unsigned_raw["signed"], unsigned_raw["signature"], unsigned_raw["signer"]) == (False, None, None)
    with pytest.raises(PackVerificationError, match="nothing to verify"):
        verify_pack(unsigned_raw, keys.public)
    for half_signed in ({**raw, "signature": None}, {**unsigned_raw, "signer": "Don Hagell"}):
        with pytest.raises(ValueError):
            BoardPack.model_validate(half_signed)


def _der(tag: int, body: bytes) -> bytes:
    n = len(body)
    return bytes([tag]) + (bytes([n]) if n < 128 else bytes([0x81, n])) + body


def _unknown_algorithm_pem(kind: str) -> str:
    """A PKCS#8 private key or SubjectPublicKeyInfo under the OID 1.2.3.4.5:
    cryptography raises UnsupportedAlgorithm, which is NOT a ValueError."""
    oid = _der(0x30, _der(0x06, bytes([0x2A, 0x03, 0x04, 0x05])))
    if kind == "PRIVATE KEY":
        der = _der(0x30, _der(0x02, b"\x00") + oid + _der(0x04, _der(0x04, bytes(32))))
    else:
        der = _der(0x30, oid + _der(0x03, b"\x00" + bytes(32)))
    return f"-----BEGIN {kind}-----\n{base64.encodebytes(der).decode('ascii')}-----END {kind}-----\n"


def _bad_keys(d: Path, public_pem: str) -> dict[str, Path]:
    d.mkdir(parents=True)
    bad = {name: d / f"{name}.pem" for name in (
        "missing", "garbage", "empty", "public-key", "not-ed25519", "encrypted", "unknown-algorithm")}
    bad["unknown-algorithm"].write_text(_unknown_algorithm_pem("PRIVATE KEY"), encoding="ascii")
    bad["directory"] = d / "a-directory"
    bad["directory"].mkdir()
    bad["garbage"].write_text("-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n")
    bad["empty"].write_text("")
    bad["public-key"].write_text(public_pem)
    pkcs8 = serialization.PrivateFormat.PKCS8
    bad["not-ed25519"].write_bytes(ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, pkcs8, serialization.NoEncryption()))
    bad["encrypted"].write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, pkcs8, serialization.BestAvailableEncryption(b"pw")))
    return bad


def test_key_load_failure_raises_and_is_never_a_process_exit(tmp_path, keys, monkeypatch):
    s = _stack(tmp_path)
    unsigned = s.engine.build(now=NOW)
    bad = _bad_keys(tmp_path / "bad", keys.public)
    for label, path in bad.items():
        # a SystemExit is not an InvalidSigningKey: it would escape and fail here
        with pytest.raises(InvalidSigningKey) as exc:
            load_signing_key(path)
        assert "not a key" not in str(exc.value) and "BEGIN" not in str(exc.value), label
        if path.is_file():
            with pytest.raises(InvalidSigningKey):
                sign_pack(unsigned, "Don Hagell", path.read_text(encoding="ascii", errors="replace"))

    def never(*a, **k):
        raise AssertionError("a refused render must not query any service")

    monkeypatch.setattr(api_module, "engine_from_env", never)
    for label, path in bad.items():
        out = tmp_path / "packs" / label
        r = runner.invoke(cli_app, ["render", "--out", str(out), "--no-pdf",
                                    "--signer", "Don Hagell", "--sign-key", str(path)])
        assert r.exit_code == 2, (label, r.output)
        assert r.stderr.startswith("refused: signing key"), (label, r.stderr)
        assert not out.exists(), label

    # the server never loads a key: signing inputs on a request change nothing
    api = TestClient(create_app(engine=s.engine))
    served = api.get("/pack", params={"signer": "Don Hagell", "sign_key": str(bad["garbage"])})
    assert served.status_code == 200 and served.json()["signed"] is False


def test_unsigned_banner_follows_body_and_the_signed_footer_names_signer_and_fingerprint(tmp_path, keys):
    s = _stack(tmp_path)
    unsigned = s.engine.build(**_around_now(), now=NOW)
    html = render_html(unsigned)
    after_body = html[html.index("<body>") + len("<body>"):].lstrip()
    assert after_body.startswith("<div class='draft-banner'>UNSIGNED DRAFT")
    assert "signed: false" in html

    signed = sign_pack(unsigned, "Don Hagell <CFO>", keys.private)
    shtml = render_html(signed)
    assert "UNSIGNED DRAFT" not in shtml and "<div class='draft-banner'>" not in shtml
    assert "signed: false" not in shtml
    footer = shtml[shtml.index("<footer>"):shtml.index("</footer>")]
    assert "Signed by <b>Don Hagell &lt;CFO&gt;</b>" in footer
    assert signed.key_fingerprint in footer and "board-pack.json" in footer
    assert "Window (range):" in shtml and f"{unsigned.window.since} → {unsigned.window.until}" in shtml


def test_cli_render_signs_and_verify_exits_0_1_1(tmp_path, keys, monkeypatch):
    s = _stack(tmp_path)
    monkeypatch.setattr(api_module, "engine_from_env", lambda org="Spin State Labs": s.engine)
    key, pub, other = (str(keys.dir / n) for n in ("signer.pem", "signer.pub.pem", "other.pub.pem"))
    window = _around_now()

    signed_dir = tmp_path / "signed"
    r = runner.invoke(cli_app, ["render", "--out", str(signed_dir), "--no-pdf", "--since", window["since"],
                                "--until", window["until"], "--signer", "Don Hagell", "--sign-key", key])
    assert r.exit_code == 0, r.output
    assert "signed by Don Hagell" in r.output
    pack_json = signed_dir / "board-pack.json"
    raw = json.loads(pack_json.read_text(encoding="utf-8"))
    assert (raw["signed"], raw["signer"], raw["window"]["kind"]) == (True, "Don Hagell", "range")
    assert _by_name_raw(raw)[ALLOW]["value"] == 3
    html = (signed_dir / "board-pack.html").read_text(encoding="utf-8")
    assert "UNSIGNED DRAFT" not in html and raw["key_fingerprint"] in html

    ok = runner.invoke(cli_app, ["verify", str(pack_json), "--pubkey", pub])
    assert ok.exit_code == 0 and "signature valid" in ok.output and "Don Hagell" in ok.output
    wrong = runner.invoke(cli_app, ["verify", str(pack_json), "--pubkey", other])
    assert wrong.exit_code == 1 and "wrong key" in wrong.stderr
    raw["sections"][2]["metrics"][1]["value"] += 1
    tampered = signed_dir / "tampered.json"
    tampered.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    bad = runner.invoke(cli_app, ["verify", str(tampered), "--pubkey", pub])
    assert bad.exit_code == 1 and "signature INVALID" in bad.stderr
    not_json = signed_dir / "not.json"
    not_json.write_text("{", encoding="utf-8")
    assert runner.invoke(cli_app, ["verify", str(not_json), "--pubkey", pub]).exit_code == 1
    for body in ("[]", "3", '"board pack"', "null"):  # JSON, but not an object: a named failure, no traceback
        not_a_pack = signed_dir / "not-a-pack.json"
        not_a_pack.write_text(body, encoding="utf-8")
        r = runner.invoke(cli_app, ["verify", str(not_a_pack), "--pubkey", pub])
        assert r.exit_code == 1 and "FAILED — not a board pack" in r.stderr, (body, r.output)

    unsigned_dir = tmp_path / "unsigned"
    r = runner.invoke(cli_app, ["render", "--out", str(unsigned_dir), "--no-pdf", "--period", "2026-Q3"])
    assert r.exit_code == 0 and "UNSIGNED DRAFT" in r.output
    assert "UNSIGNED DRAFT" in (unsigned_dir / "board-pack.html").read_text(encoding="utf-8")
    nothing = runner.invoke(cli_app, ["verify", str(unsigned_dir / "board-pack.json"), "--pubkey", pub])
    assert nothing.exit_code == 1 and "nothing to verify" in nothing.stderr

    for n, argv in enumerate((["--period", "Q3 2026 (demo)"], ["--period", "2026-Q3", "--since", window["since"]],
                              ["--since", "yesterday"], ["--signer", "   ", "--sign-key", key],
                              ["--signer", "Don Hagell"], ["--sign-key", key])):
        out = tmp_path / "refused" / str(n)
        r = runner.invoke(cli_app, ["render", "--out", str(out), "--no-pdf", *argv])
        assert r.exit_code == 2 and r.stderr.startswith("refused: "), (argv, r.output)
        assert not out.exists(), argv


def _metric_block(text: str, name: str) -> tuple[int, int]:
    """(start, end) of the metric object named ``name`` in indent=2 pack JSON."""
    start = text.index(f'"name": {json.dumps(name)}')
    return start, text.index("}", start)


def test_verify_refuses_a_duplicated_key_a_non_finite_number_and_a_respelled_signature(tmp_path, keys):
    """C4R-3/C4R-12: json.loads keeps the LAST of two equal keys, so a file whose
    FIRST `value` (what a human or a first-wins parser reads) is forged used to
    verify. The file is parsed strictly; the signature string has one spelling;
    a valid signature over something that is not a BoardPack is refused."""
    s = _stack(tmp_path)
    signed = sign_pack(s.engine.build(**_around_now(), now=NOW), "Don Hagell", keys.private)
    text = signed.model_dump_json(indent=2)  # exactly what `attest render` writes
    pub = str(keys.dir / "signer.pub.pem")

    def verify_text(label: str, body: str):
        path = tmp_path / f"{label}.json"
        path.write_text(body, encoding="utf-8")
        return runner.invoke(cli_app, ["verify", str(path), "--pubkey", pub])

    assert verify_text("as-written", text).exit_code == 0
    start, end = _metric_block(text, ALLOW)
    real_value = f'"value": {_by_name(signed)[ALLOW].value},'
    assert text.count(real_value, start, end) == 1
    forged_first = text[:start] + text[start:end].replace(real_value, '"value": 999,\n      ' + real_value) + text[end:]
    first_wins = json.loads(forged_first, object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    assert _by_name_raw(first_wins)[ALLOW]["value"] == 999  # what the reader of the file sees
    assert verify_pack(json.loads(forged_first), keys.public)  # last-wins parsing alone would accept it
    tampered = {
        "duplicate-value": (forged_first, "duplicate key 'value'"),
        "duplicate-signer": (text.replace('"signer": "Don Hagell",', '"signer": "Mallory",\n  "signer": "Don Hagell",', 1),
                             "duplicate key 'signer'"),
        "duplicate-signature": (text.replace('"signature": ', '"signature": "AAAA",\n  "signature": ', 1),
                                "duplicate key 'signature'"),
        "nan": (text.replace(real_value, '"value": NaN,', 1), "NaN is not a JSON number"),
        "infinity": (text.replace(real_value, '"value": -Infinity,', 1), "-Infinity is not a JSON number"),
        "overflow": (text.replace(real_value, '"value": 1e999,', 1), "1e999 overflows"),
    }
    for label, (body, reason) in tampered.items():
        assert body != text, label
        r = verify_text(label, body)
        assert r.exit_code == 1 and r.stderr.startswith(f"FAILED — not canonical JSON: {reason}"), (label, r.output)
        with pytest.raises(PackVerificationError):
            parse_pack_json(body)

    # the signature string sits outside the signed bytes, so it gets ONE spelling
    sig = signed.signature
    assert len(sig) == 88 and sig.endswith("==")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    last = alphabet.index(sig[-3])
    same_bytes = sig[:-3] + alphabet[last | 1 if last % 2 == 0 else last & ~1] + "=="  # unused low bits flipped
    assert base64.b64decode(same_bytes) == base64.b64decode(sig) and same_bytes != sig
    for label, respelled in (("junk", sig[:10] + "!! *" + sig[10:]), ("unused-bits", same_bytes),
                             ("no-padding", sig.rstrip("=")), ("newline", sig[:44] + "\\n" + sig[44:])):
        r = verify_text(f"sig-{label}", text.replace(sig, respelled, 1))
        assert r.exit_code == 1 and "not one canonical base64 Ed25519 signature" in r.stderr, (label, r.output)

    # a public key cryptography cannot load (UnsupportedAlgorithm, not a ValueError) is a named failure
    unknown = keys.dir / "unknown-algorithm.pub.pem"
    unknown.write_text(_unknown_algorithm_pem("PUBLIC KEY"), encoding="ascii")
    with pytest.raises(PackVerificationError, match="supplied public key is not usable"):
        verify_pack(json.loads(text), unknown.read_text(encoding="ascii"))
    r = runner.invoke(cli_app, ["verify", str(tmp_path / "as-written.json"), "--pubkey", str(unknown)])
    assert r.exit_code == 1 and "supplied public key is not usable" in r.stderr, r.output

    # a VALID signature by the same key over an object that is not a board pack
    # (e.g. another verb signing a mapping with the same canonical JSON) is refused
    impostor = {"signed": True, "signer": "Don Hagell", "signed_at": NOW.isoformat(),
                "key_fingerprint": key_fingerprint(keys.public), "approved": "everything"}
    impostor["signature"] = sign_manifest({k: v for k, v in impostor.items()}, keys.private)
    with pytest.raises(PackVerificationError, match="not a board pack"):
        verify_pack(impostor, keys.public)
    r = verify_text("impostor", json.dumps(impostor, indent=2))
    assert r.exit_code == 1 and "not a board pack" in r.stderr, r.output


# --- served --------------------------------------------------------------------------------


def test_served_pack_honours_since_until_and_period_and_is_always_unsigned(tmp_path, keys):
    s = _stack(tmp_path)
    api = TestClient(create_app(engine=s.engine))
    window = _around_now()

    r = api.get("/pack", params=window)
    assert r.status_code == 200
    body = r.json()
    assert body["window"]["kind"] == "range"
    assert body["window"]["since"] == normalise_bound("since", window["since"], end=False).isoformat()
    assert (body["signed"], body["signer"], body["signed_at"], body["key_fingerprint"], body["signature"]) == (
        False, None, None, None, None)
    assert _by_name_raw(body)[ALLOW]["value"] == 3
    served = BoardPack.model_validate(body)
    rendered = s.engine.build(**window)
    key = lambda m: (m.name, m.value, m.unit, m.status, m.source_query, m.note, m.basis)  # noqa: E731
    assert [key(m) for m in served.all_metrics()] == [key(m) for m in rendered.all_metrics()]

    # a window that excludes the staged events counts 0 — never all-time relabelled
    past = _by_name_raw(api.get("/pack", params={"since": "2020-01-01", "until": "2020-12-31"}).json())
    assert past[ALLOW]["value"] == 0 and "until=2020-12-31T23:59:59.999999%2B00:00" in past[ALLOW]["source_query"]
    quarter = api.get("/pack", params={"period": "2026-Q3"}).json()["window"]
    assert (quarter["kind"], quarter["since"], quarter["until"]) == ("quarter", *Q3)
    assert api.get("/pack", params={"period": "Q3 2026"}).json()["period"] == "Q3 2026"  # the caller's label
    html = api.get("/pack.html", params=window)
    assert html.status_code == 200 and "UNSIGNED DRAFT" in html.text

    for params in ({"period": "Q3 2026 (demo)"}, {"period": "2026-Q3", "since": "2026-07-01"},
                   {"since": "2026-09-14", "until": "2026-09-13"}, {"since": "yesterday"}, {"period": ""}):
        for route in ("/pack", "/pack.html"):
            refused = api.get(route, params=params)
            assert refused.status_code == 422, (route, params)
            assert "sections" not in refused.text

    # an engine that signs is refused: the served pack is ALWAYS an unsigned draft
    signing = copy.copy(s.engine)
    signing.build = lambda **k: sign_pack(PackEngine.build(s.engine, **k), "Unattended server", keys.private)
    refused = TestClient(create_app(engine=signing)).get("/pack")
    assert refused.status_code == 500 and "unsigned drafts" in refused.json()["detail"]
    source = Path(api_module.__file__).read_text(encoding="utf-8")
    assert "sign_pack" not in source and "attestation_reporter.signing" not in source
