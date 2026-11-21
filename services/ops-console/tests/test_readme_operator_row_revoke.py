"""README "Operator name is mandatory" row, pinned to what the code does.

The row once said the operator name is mandatory on EVERY mutation. Token
revoke takes no operator in its request (``POST /api/tokens/{id}/revoke`` has
no body); the human is identified only by the ``x-field-operator*`` headers,
which the console forwards, and which it requires (401) only under ENFORCE.
These tests pin the behaviour per operator-layer mode and the README wording
that states it, so the row cannot drift again.
"""

from __future__ import annotations

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
