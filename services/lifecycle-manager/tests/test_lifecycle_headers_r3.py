"""Key rotation R3 (design 2026-10-27 section 8 row 3, finding F11): the
lifecycle service's own delegation and kill-switch clients read their auth
headers on EVERY request, so a rotated ``svc-lifecycle`` key file is used on
the next call without a restart.

Pinned here:

* a key file replaced mid-run (temp file + atomic rename, the runbook's only
  edit method) is sent on the very next request, through the client that
  ``create_app`` built once at startup (``api.py`` app-build line) and through
  a served ``POST /sweep``;
* a key file that goes missing or empty mid-run sends NO operator pair on the
  next request (fail closed), and a client built while the file is missing or
  empty sends exactly what the old build-time client sent;
* for an unchanged key the request bytes (method, URL, raw header list in
  order, body) equal those of the client this replaces,
  ``httpx.Client(headers=auth_headers())``.

Every key below is an obviously fake test value.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core import authn
from field_core import operator_auth as oa
from field_core.clients import LedgerClient, RegistryClient
from lifecycle_manager import api as api_module
from lifecycle_manager.api import create_app, delegation_client, killswitch_client
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

OPERATOR = "svc-lifecycle"
KEY_OLD = "fok_r3-fake-old-key-0000000000000000"
KEY_NEW = "fok_r3-fake-new-key-1111111111111111"
KEY_ENV = "fok_r3-fake-env-key-2222222222222222"
SECRET = "r3-fake-perimeter-secret"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner,department\nAP Team Lead,finance\nController Spin State,finance\n"
OP_HEADERS = (oa.HEADER_OPERATOR, oa.HEADER_KEY)
BUILDERS = {"delegation": delegation_client, "killswitch": killswitch_client}


@pytest.fixture(autouse=True)
def _scrubbed(monkeypatch):
    for name in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
                 oa.ENV_OPERATOR_KEY_FILE, authn.ENV_VAR):
        monkeypatch.delenv(name, raising=False)


def write_key(path: Path, key: str) -> None:
    """The runbook's rotation: a temp file in the same directory, then an
    atomic rename onto the live name (never an in-place rewrite)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(key + "\n", encoding="utf-8")
    os.replace(tmp, path)


@pytest.fixture()
def key_file(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "keys" / f"{OPERATOR}.key"
    path.parent.mkdir()
    write_key(path, KEY_OLD)
    monkeypatch.setenv(oa.ENV_OPERATOR, OPERATOR)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(path))
    return path


class Recorder:
    """A transport that records each request as sent and answers 200 (or
    forwards to an in-process app when one is given)."""

    def __init__(self, forward: TestClient | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self._forward = forward

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if self._forward is None:
            return httpx.Response(200, json={"ok": True})
        resp = self._forward.request(
            request.method, request.url.path, params=request.url.params,
            content=request.content,
            headers={k: v for k, v in request.headers.items()
                     if k.lower() not in ("host", "content-length")})
        return httpx.Response(resp.status_code, content=resp.content,
                              headers={"content-type": resp.headers.get(
                                  "content-type", "application/json")})

    def last_operator_pair(self) -> tuple[str | None, str | None]:
        h = self.requests[-1].headers
        return h.get(oa.HEADER_OPERATOR), h.get(oa.HEADER_KEY)


def route(client: httpx.Client, recorder: Recorder) -> httpx.Client:
    """Point an already-built client at the recorder (the client object itself,
    and whatever it captured when it was built, is what is under test)."""
    client._transport = httpx.MockTransport(recorder)
    client._mounts = {}
    return client


# --- the rotated key is used on the next request ----------------------------------


@pytest.mark.parametrize("which", sorted(BUILDERS))
def test_a_key_file_replaced_mid_run_is_sent_on_the_next_request(key_file, which):
    rec = Recorder()
    client = route(BUILDERS[which](), rec)
    client.get("/tokens")
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)
    write_key(key_file, KEY_NEW)
    client.post("/kill/a1", json={"reason": "r3"})
    assert rec.last_operator_pair() == (OPERATOR, KEY_NEW)
    write_key(key_file, KEY_OLD)  # and back again: nothing is cached either way
    client.get("/tokens")
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)


@pytest.fixture()
def estate(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FIELD_LIFECYCLE_ROSTER", raising=False)
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t"),
    ))
    registry.post("/agents", json={
        "agent_id": "invoicing-agent", "name": "Invoicing",
        "owner": "AP Team Lead", "domain": "finance"})
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller Spin State",
        "scope": ["draft invoices"],
        "expires_at": (NOW + timedelta(days=10)).isoformat()})
    return registry, ledger, delegation


def test_the_startup_delegation_client_of_a_served_app_sends_the_rotated_key(estate, key_file):
    """F11 exactly: ``create_app`` builds the delegation client ONCE; a sweep
    after the rotation must reach delegation-authority with the new key."""
    registry, ledger, delegation = estate
    app = create_app(registry=RegistryClient(client=registry, base_url="http://t"),
                     ledger=LedgerClient(client=ledger, base_url="http://t"))
    rec = Recorder(forward=delegation)
    route(app.state.delegation, rec)
    served = TestClient(app)

    first = served.post("/sweep", json={"roster_csv": ROSTER})
    assert first.status_code == 200, first.text
    assert first.json()["tokens_scanned"] == 1  # the forwarded call really answered
    assert rec.requests and rec.requests[-1].url.path == "/tokens"
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)

    write_key(key_file, KEY_NEW)
    calls_before = len(rec.requests)
    second = served.post("/sweep", json={"roster_csv": ROSTER})
    assert second.status_code == 200, second.text
    assert len(rec.requests) > calls_before
    assert rec.last_operator_pair() == (OPERATOR, KEY_NEW)


def test_an_env_key_changed_mid_run_is_sent_on_the_next_request(monkeypatch):
    """Without a key file the env key is read per request too (same reader)."""
    monkeypatch.setenv(oa.ENV_OPERATOR, OPERATOR)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_ENV)
    rec = Recorder()
    client = route(delegation_client(), rec)
    client.get("/tokens")
    assert rec.last_operator_pair() == (OPERATOR, KEY_ENV)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_NEW)
    client.get("/tokens")
    assert rec.last_operator_pair() == (OPERATOR, KEY_NEW)


# --- missing / empty key file: fail closed, exactly as today -------------------


@pytest.mark.parametrize("which", sorted(BUILDERS))
@pytest.mark.parametrize("damage", ["missing", "empty", "two_tokens"])
def test_a_key_file_that_goes_bad_mid_run_sends_no_operator_pair(key_file, monkeypatch,
                                                                  which, damage):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    rec = Recorder()
    client = route(BUILDERS[which](), rec)
    client.get("/tokens")
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)
    if damage == "missing":
        key_file.unlink()
    elif damage == "empty":
        key_file.write_text("", encoding="utf-8")
    else:
        key_file.write_text(f"{KEY_OLD} {KEY_NEW}\n", encoding="utf-8")
    client.get("/tokens")
    sent = rec.requests[-1].headers
    assert not [h for h in OP_HEADERS if h in sent], "a bad key file must send no operator pair"
    assert KEY_OLD not in str(sent.raw)
    assert sent.get(authn.HEADER) == SECRET  # the perimeter header is unaffected


@pytest.mark.parametrize("which", sorted(BUILDERS))
@pytest.mark.parametrize("damage", ["missing", "empty"])
def test_a_client_built_with_a_bad_key_file_sends_what_the_old_client_sent(key_file, monkeypatch,
                                                                             which, damage):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    if damage == "missing":
        key_file.unlink()
    else:
        key_file.write_text("", encoding="utf-8")
    new, old = Recorder(), Recorder()
    route(BUILDERS[which](), new).get("/tokens")
    legacy_client(which, old).get("/tokens")
    assert new.requests[0].headers.raw == old.requests[0].headers.raw
    assert not [h for h in OP_HEADERS if h in new.requests[0].headers]


# --- wire bytes identical for an unchanged key --------------------------------------


def legacy_client(which: str, recorder: Recorder) -> httpx.Client:
    """The construction this slice replaces: headers fixed at build time."""
    base = {"delegation": "http://127.0.0.1:8003", "killswitch": "http://127.0.0.1:8005"}[which]
    return httpx.Client(base_url=base, timeout=10.0, headers=authn.auth_headers(),
                        transport=httpx.MockTransport(recorder))


CALLS = [
    ("GET", "/tokens", {}),
    ("GET", "/tokens", {"params": {"agent_id": "invoicing-agent"}}),
    ("POST", "/tokens/t-1/revoke", {}),
    ("POST", "/kill/a1", {"json": {"reason": "orphan", "operator": "lifecycle-manager"}}),
    ("POST", "/tokens", {"content": b"raw-body", "headers": {"content-type": "text/plain"}}),
    ("GET", "/tokens", {"headers": {"x-extra": "1", "User-Agent": "r3-test-agent"}}),
    ("GET", "/tokens", {"headers": [("x-dup", "a"), ("x-dup", "b")]}),
    ("GET", "/tokens", {"headers": {authn.HEADER: "per-call-override"}}),
    ("GET", "/tokens", {"headers": {oa.HEADER_KEY: "fok_per-call-override"}}),
]


def wire(request: httpx.Request) -> tuple:
    return (request.method, str(request.url), list(request.headers.raw), request.content)


@pytest.mark.parametrize("which", sorted(BUILDERS))
@pytest.mark.parametrize("config", ["secret+file", "secret+env", "file", "secret", "nothing"])
def test_wire_bytes_equal_the_build_time_client_for_an_unchanged_key(tmp_path, monkeypatch,
                                                                     which, config):
    if "secret" in config:
        monkeypatch.setenv(authn.ENV_VAR, SECRET)
    if "file" in config:
        path = tmp_path / f"{OPERATOR}.key"
        write_key(path, KEY_OLD)
        monkeypatch.setenv(oa.ENV_OPERATOR, OPERATOR)
        monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(path))
    if "env" in config:
        monkeypatch.setenv(oa.ENV_OPERATOR, OPERATOR)
        monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_ENV)
    new, old = Recorder(), Recorder()
    client, legacy = route(BUILDERS[which](), new), legacy_client(which, old)
    for method, url, kw in CALLS:
        client.request(method, url, **kw)
        legacy.request(method, url, **kw)
    assert len(new.requests) == len(old.requests) == len(CALLS)
    for got, want in zip(new.requests, old.requests):
        assert wire(got) == wire(want)
    assert client.timeout == legacy.timeout and client.base_url == legacy.base_url


def test_the_wire_check_is_not_vacuous(key_file, monkeypatch):
    """The equality above would hold trivially if neither client sent auth."""
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    rec = Recorder()
    route(delegation_client(), rec).get("/tokens")
    names = [k.lower() for k, _ in rec.requests[0].headers.raw]
    assert names[-3:] == [authn.HEADER.encode(), oa.HEADER_OPERATOR.encode(), oa.HEADER_KEY.encode()]


# --- structure: nothing is captured at build time ------------------------------------


@pytest.mark.parametrize("which", sorted(BUILDERS))
def test_the_clients_hold_no_auth_header_of_their_own(key_file, monkeypatch, which):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    client = BUILDERS[which]()
    held = {k.lower() for k in client.headers}
    assert not held & {authn.HEADER, *OP_HEADERS}, held
    assert isinstance(client, api_module.PerRequestAuthClient)


# --- C-486: the clients never read the proxy environment ------------------------------


@pytest.mark.parametrize("which", sorted(BUILDERS))
def test_the_clients_ignore_a_proxy_in_the_environment(key_file, monkeypatch, which):
    for var in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(var, "http://127.0.0.1:9")
    client = BUILDERS[which]()
    assert client.trust_env is False
    # no proxy transport is mounted for an http target: the request would go straight to the service
    assert client._transport_for_url(httpx.URL("http://registry:8001/x")) is client._transport


def test_an_explicit_trust_env_cannot_turn_it_back_on(key_file):
    assert api_module.PerRequestAuthClient(trust_env=True).trust_env is False
