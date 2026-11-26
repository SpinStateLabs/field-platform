"""README "Operator name is mandatory" row, pinned to what the code does.

The row once said the operator name is mandatory on EVERY mutation. Token
revoke takes no operator in its request (``POST /api/tokens/{id}/revoke`` has
no body); the human is identified only by the ``x-field-operator*`` headers,
which the console forwards, and which it requires (401) only under ENFORCE.
These tests pin the behaviour per operator-layer mode and the README wording
that states it, so the row cannot drift again.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from ops_console.api import ServiceClient, create_app

README = Path(__file__).resolve().parents[1] / "README.md"
H = {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: "fok_don_key_0123456789"}


class Rec:
    def __init__(self):
        self.calls = []

    def post(self, path, **kw):
        self.calls.append((path, kw))

        class R:
            status_code = 200

            def json(self):
                return {"ok": True}

        return R()

    def get(self, path, **kw):
        raise ConnectionError("n/a")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def console():
    dg, other = Rec(), Rec()
    sc = lambda c: ServiceClient(client=c, base_url="http://t")  # noqa: E731
    app = create_app(registry=sc(other), ledger=sc(other), delegation=sc(dg),
                     governor=sc(other), killswitch=sc(other), sentinel=sc(other))
    return TestClient(app), dg


def test_off_revoke_needs_no_operator_and_forwards_none(console):
    c, dg = console
    assert oa.mode() == oa.OFF
    assert c.post("/api/tokens/t1/revoke").status_code == 200
    assert "headers" not in dg.calls[-1][1]


def test_log_only_revoke_still_needs_no_operator(console, monkeypatch):
    c, dg = console
    monkeypatch.setenv(oa.ENV_REGISTRY, "operators.json")   # a path; the console never opens it
    assert oa.mode() == oa.LOG_ONLY
    assert c.post("/api/tokens/t1/revoke").status_code == 200
    assert "headers" not in dg.calls[-1][1]


def test_enforce_revoke_without_headers_is_401_and_not_proxied(console, monkeypatch):
    c, dg = console
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    assert c.post("/api/tokens/t1/revoke").status_code == 401
    assert dg.calls == []


def test_enforce_revoke_with_headers_forwards_exactly_the_human_pair(console, monkeypatch):
    c, dg = console
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    assert c.post("/api/tokens/t1/revoke", headers=H).status_code == 200
    assert dg.calls[-1][1]["headers"] == {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: H[oa.HEADER_KEY]}


MODES = ("off", "log_only", "enforce")


def _set_mode(monkeypatch, mode, tmp_path=None):
    if mode in ("log_only", "enforce"):
        monkeypatch.setenv(oa.ENV_REGISTRY, str(tmp_path / "operators.json") if tmp_path else "operators.json")
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


@pytest.mark.parametrize("mode", MODES)
def test_well_formed_pair_is_forwarded_in_every_mode(console, monkeypatch, mode):
    c, dg = console
    _set_mode(monkeypatch, mode)
    assert c.post("/api/tokens/t1/revoke", headers=H).status_code == 200
    assert dg.calls[-1][1]["headers"] == {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: H[oa.HEADER_KEY]}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad", [
    {oa.HEADER_OPERATOR: "bad name!", oa.HEADER_KEY: H[oa.HEADER_KEY]},   # outside the charset
    {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: "bad key!"},               # key outside the charset
    {oa.HEADER_OPERATOR: "x" * 65, oa.HEADER_KEY: H[oa.HEADER_KEY]},      # oversize
    {oa.HEADER_OPERATOR: "", oa.HEADER_KEY: H[oa.HEADER_KEY]},            # empty
])
def test_malformed_header_is_400_in_every_mode_and_not_proxied(console, monkeypatch, mode, bad):
    c, dg = console
    _set_mode(monkeypatch, mode)
    assert c.post("/api/tokens/t1/revoke", headers=bad).status_code == 400
    assert dg.calls == []


@pytest.mark.parametrize("mode,status", [("off", 200), ("log_only", 200), ("enforce", 401)])
def test_half_pair_is_dropped_in_off_and_log_only_and_401_in_enforce(console, monkeypatch, mode, status):
    c, dg = console
    _set_mode(monkeypatch, mode)
    r = c.post("/api/tokens/t1/revoke", headers={oa.HEADER_OPERATOR: "don"})
    assert r.status_code == status
    if status == 200:
        assert "headers" not in dg.calls[-1][1]          # dropped silently, nothing forwarded
    else:
        assert dg.calls == []


def test_a_blank_kill_operator_is_refused_by_the_console_and_nothing_is_sent():
    # As the kill-switch does: empty and whitespace-only are both 422 here.
    kill = Rec()
    sc = lambda c: ServiceClient(client=c, base_url="http://t")  # noqa: E731
    other = Rec()
    app = create_app(registry=sc(other), ledger=sc(other), delegation=sc(other),
                     governor=sc(other), killswitch=sc(kill), sentinel=sc(other))
    c = TestClient(app)
    assert c.post("/api/agents/a1/kill", json={"operator": ""}).status_code == 422
    assert kill.calls == []
    assert c.post("/api/agents/a1/kill", json={"operator": " "}).status_code == 422
    assert kill.calls == []


def test_real_governor_replaces_resolved_by_with_the_authenticated_id(tmp_path, monkeypatch):
    """The README sentence about resolve, against the REAL spend-governor app
    (in the CI install set): authenticated -> stored resolved_by is the
    operator id; unauthenticated -> as typed."""
    from spend_governor.api import create_app as gov_app
    from spend_governor.core import GovernorStore

    key = "fok_don-key-0123456789abcdef"
    reg = tmp_path / "operators.json"
    reg.write_text(json.dumps([{"operator_id": "don", "key_sha256": oa.key_sha256(key),
                                "status": "active", "scopes": ["*"]}]))
    store = GovernorStore(tmp_path / "g.sqlite3")
    gc = TestClient(gov_app(store=store))
    ids = []
    for agent in ("a1", "a2", "a3"):
        assert gc.put(f"/caps/{agent}", json={"agent_id": agent, "limit_cents": 100, "period": "total",
                                              "escalate_at_pct": 80}).status_code == 200
        assert gc.post("/spend", json={"agent_id": agent, "cents": 90}).status_code == 201
        ids.append(gc.get("/escalations", params={"agent_id": agent}).json()[0]["escalation_id"])
    pair = {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: key}
    body = {"resolved_by": "Typed Name"}

    r = gc.post(f"/escalations/{ids[0]}/resolve", json=body)                   # OFF
    assert (r.status_code, r.json()["resolved_by"]) == (200, "Typed Name")

    monkeypatch.setenv(oa.ENV_REGISTRY, str(reg))                              # LOG-ONLY
    r = gc.post(f"/escalations/{ids[1]}/resolve", json=body, headers=pair)
    assert (r.status_code, r.json()["resolved_by"]) == (200, "don")

    monkeypatch.setenv(oa.ENV_REQUIRE, "1")                                    # ENFORCE
    assert gc.post(f"/escalations/{ids[2]}/resolve", json=body).status_code == 401
    r = gc.post(f"/escalations/{ids[2]}/resolve", json=body, headers=pair)
    assert (r.status_code, r.json()["resolved_by"]) == (200, "don")
    store.close()


def _row() -> str:
    rows = [ln for ln in README.read_text().splitlines() if ln.startswith("| Operator name")]
    assert len(rows) == 1, rows
    return rows[0]


def test_readme_row_does_not_claim_every_mutation():
    assert "mandatory on every mutation" not in _row().lower()


def test_readme_row_states_what_revoke_does():
    row = _row().lower()
    for needle in ("revoke", "no operator", "off", "log-only", "enforce", "401",
                   "x-field-operator", "resolve", "422"):
        assert needle in row, needle


def test_readme_intro_does_not_claim_a_mandatory_name_for_every_action():
    assert "(operator name is mandatory)" not in README.read_text()


def test_readme_row_pins_the_corrected_sentences():
    row = " ".join(_row().split())
    # forwarding: every mode, only when well-formed pair present
    assert "whenever the request carries a well-formed one, in every mode" in row
    assert "the console forwards none" not in row
    # no pair: OFF/LOG-ONLY proceed, ENFORCE 401
    assert "With no pair, OFF and LOG-ONLY proceed (200) and ENFORCE answers **401** and proxies nothing" in row
    # half pair and malformed header
    assert "half pair" in row and "dropped silently in OFF and LOG-ONLY" in row
    assert "malformed operator header is **400** in every mode" in row
    assert "and the revoke proceeds (200)" not in row
    # resolve: replaced when authenticated, not "not checked"
    assert "not checked" not in row
    assert "the governor replaces it with the authenticated id" in row
    assert "bind_body_operator" in row and "recorded as typed" in row
    # empty and whitespace-only alike
    assert "422 on an empty or whitespace-only `operator`" in row


def test_readme_intro_says_headers_are_forwarded_whenever_well_formed():
    assert "forwarded whenever well-formed and required under ENFORCE" in " ".join(README.read_text().split())
