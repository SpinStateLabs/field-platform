"""Phase G C-12 follow-up (guards ruling, "per-call headers on RegistryClient.set_status"):
the kill-switch sends ``x-field-operator-on-behalf-of`` through field-core's PUBLIC
``RegistryClient.set_status(..., extra_headers=...)`` on every status write it makes for an
authenticated caller (kill, domain kill, revive, the drill's kill and its restore), and
never reaches into the client's private request pieces.

The failure this prevents (review of PR #41, finding on the private reach): with the
kill-switch reading ``_client``, ``_base``, ``_own_client`` and ``_request_auth``, a
field-core refactor that renamed any of them turned every authenticated kill, revive and
drill into a 502 (denial of kill), and a production wrapper would have dropped the header
silently. The wire bytes are pinned, unchanged, by tests/test_on_behalf_of_c12_kill_switch.py.

Real kill-switch + registry + sealed-ledger apps over TestClient. Test key values are
throwaway constants."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import kill_switch.api as ks_api
from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

BODY = {"operator": "Don Hagell", "reason": "c12 public api"}
KEY_DON = "tkv-c12p-don-key-0123456789abcdef"
KEY_KSVC = "tkv-c12p-ksvc-key-0123456789abcdef"
OBO = "x-field-operator-on-behalf-of"


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def calls(monkeypatch):
    """Every RegistryClient.set_status call, with its keyword arguments. The recorder
    replaces the class attribute, so it IS ``RegistryClient.set_status`` (the kill-switch's
    "not a wrapper" test still holds) and it calls the real method."""
    seen: list[tuple[str, str, dict]] = []
    real = RegistryClient.set_status

    def recording(self, agent_id, status, **kwargs):
        seen.append((agent_id, status, kwargs))
        return real(self, agent_id, status, **kwargs)

    monkeypatch.setattr(RegistryClient, "set_status", recording)
    return seen


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps([
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
         "scopes": ["*"]},
        {"operator_id": "svc-killswitch", "key_sha256": oa.key_sha256(KEY_KSVC), "status": "active",
         "scopes": ["kill", "revive", "drill", "bypass_operator_list", "ledger_attribute"],
         "event_prefixes": ["kill.", "registry."]},
    ]), encoding="utf-8")
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
    registry = TestClient(create_registry_app(
        store=RegistryStore(tmp_path / "a.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t")))
    svc = hdr("svc-killswitch", KEY_KSVC)
    registry.headers.update(svc)
    ledger.headers.update(svc)
    kill = TestClient(create_kill_app(
        registry=RegistryClient(client=registry, base_url="http://t"),
        ledger=LedgerClient(client=ledger, base_url="http://t")))
    for agent in ("a1", "a2"):
        assert registry.post("/agents", json={"agent_id": agent, "name": agent, "owner": "O",
                                              "domain": "finance"}).status_code == 201
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")       # ENFORCE: an unnamed bypass PATCH is a 403
    return kill


def test_every_status_write_for_an_authenticated_caller_goes_through_the_public_argument(stack, calls):
    don = hdr("don", KEY_DON)
    assert stack.post("/kill/a1", json=BODY, headers=don).status_code == 200
    assert stack.post("/revive/a1", json=BODY, headers=don).status_code == 200
    r = stack.post("/drill/a1", json=BODY, headers=don)
    assert r.status_code == 200 and r.json()["restored"] is True
    assert stack.post("/kill/domain/finance", json=BODY, headers=don).status_code == 200
    named = {"extra_headers": {OBO: "don"}}
    assert calls == [
        ("a1", "killed", named),     # kill
        ("a1", "active", named),     # revive
        ("a1", "killed", named),     # drill: kill
        ("a1", "active", named),     # drill: restore
        ("a1", "killed", named),     # domain kill, one write per agent
        ("a2", "killed", named),
    ]


def test_flags_off_calls_set_status_exactly_as_before(stack, calls, monkeypatch):
    monkeypatch.delenv(oa.ENV_REGISTRY)
    monkeypatch.delenv(oa.ENV_REQUIRE)
    assert stack.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert calls == [("a1", "killed", {})]


def test_the_kill_switch_reaches_no_private_registry_client_piece():
    """Static pin: no ``registry._<anything>`` attribute and no private name imported from
    field_core in kill_switch/api.py (a renamed private would be a 502 on every kill)."""
    tree = ast.parse(Path(ks_api.__file__).read_text(encoding="utf-8"))
    private_attrs = sorted({f"{n.value.id}.{n.attr}" for n in ast.walk(tree)
                            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                            and n.value.id == "registry" and n.attr.startswith("_")})
    private_imports = sorted({f"{n.module}.{a.name}" for n in ast.walk(tree)
                              if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("field_core")
                              for a in n.names if a.name.startswith("_")})
    assert private_attrs == [] and private_imports == [], (private_attrs, private_imports)
