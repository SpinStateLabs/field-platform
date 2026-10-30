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
import re
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
from field_core import guarded_operator as go
from field_core.guarded_operator import (DELEGATION_GUARDED, KILLSWITCH_GUARDED, is_guarded_path,
                                         perimeter_headers)
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
#: C-511: the operator pair rides only a guarded route of the target; one guarded write per builder
GUARDED = {"delegation": ("POST", "/tokens/t-1/revoke"), "killswitch": ("POST", "/kill/a1")}
TABLES = {"delegation": DELEGATION_GUARDED, "killswitch": KILLSWITCH_GUARDED}


def guarded_call(client: httpx.Client, which: str) -> httpx.Response:
    method, path = GUARDED[which]
    return client.request(method, path)


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
    guarded_call(client, which)
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)
    write_key(key_file, KEY_NEW)
    guarded_call(client, which)
    assert rec.last_operator_pair() == (OPERATOR, KEY_NEW)
    write_key(key_file, KEY_OLD)  # and back again: nothing is cached either way
    guarded_call(client, which)
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
    assert rec.last_operator_pair() == (None, None)                 # C-511: the sweep only READS
    app.state.delegation.post("/tokens/t-1/revoke")                  # a guarded write, same client object
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)

    write_key(key_file, KEY_NEW)
    calls_before = len(rec.requests)
    second = served.post("/sweep", json={"roster_csv": ROSTER})
    assert second.status_code == 200, second.text
    assert len(rec.requests) > calls_before
    assert rec.last_operator_pair() == (None, None)
    app.state.delegation.post("/tokens/t-1/revoke")
    assert rec.last_operator_pair() == (OPERATOR, KEY_NEW)


def test_an_env_key_changed_mid_run_is_sent_on_the_next_request(monkeypatch):
    """Without a key file the env key is read per request too (same reader)."""
    monkeypatch.setenv(oa.ENV_OPERATOR, OPERATOR)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_ENV)
    rec = Recorder()
    client = route(delegation_client(), rec)
    guarded_call(client, "delegation")
    assert rec.last_operator_pair() == (OPERATOR, KEY_ENV)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_NEW)
    guarded_call(client, "delegation")
    assert rec.last_operator_pair() == (OPERATOR, KEY_NEW)


# --- missing / empty key file: fail closed, exactly as today -------------------


@pytest.mark.parametrize("which", sorted(BUILDERS))
@pytest.mark.parametrize("damage", ["missing", "empty", "two_tokens"])
def test_a_key_file_that_goes_bad_mid_run_sends_no_operator_pair(key_file, monkeypatch,
                                                                  which, damage):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    rec = Recorder()
    client = route(BUILDERS[which](), rec)
    guarded_call(client, which)
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)
    if damage == "missing":
        key_file.unlink()
    elif damage == "empty":
        key_file.write_text("", encoding="utf-8")
    else:
        key_file.write_text(f"{KEY_OLD} {KEY_NEW}\n", encoding="utf-8")
    guarded_call(client, which)
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


def legacy_client(which: str, recorder: Recorder, reads: bool = False) -> httpx.Client:
    """The construction this slice replaces: headers fixed at build time. ``reads=True``: the same client as
    it is for a request that is not a guarded write (C-511), i.e. the perimeter secret only."""
    base = {"delegation": "http://127.0.0.1:8003", "killswitch": "http://127.0.0.1:8005"}[which]
    return httpx.Client(base_url=base, timeout=10.0,
                        headers=perimeter_headers() if reads else authn.auth_headers(),
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
    new, old, old_reads = Recorder(), Recorder(), Recorder()
    client, legacy = route(BUILDERS[which](), new), legacy_client(which, old)
    legacy_read = legacy_client(which, old_reads, reads=True)
    for method, url, kw in CALLS:
        client.request(method, url, **kw)
        legacy.request(method, url, **kw)
        legacy_read.request(method, url, **kw)
    assert len(new.requests) == len(old.requests) == len(old_reads.requests) == len(CALLS)
    for (method, url, _), got, want, want_read in zip(CALLS, new.requests, old.requests, old_reads.requests):
        if is_guarded_path(method, url, TABLES[which]):
            assert wire(got) == wire(want)                       # a guarded write: the very same bytes as before
        else:                                                    # C-511: anything else = the perimeter secret only
            assert wire(got) == wire(want_read)
    assert client.timeout == legacy.timeout and client.base_url == legacy.base_url


def test_the_wire_check_is_not_vacuous(key_file, monkeypatch):
    """The equality above would hold trivially if neither client sent auth."""
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    rec = Recorder()
    route(delegation_client(), rec).post("/tokens/t-1/revoke")
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


# --- C-511: the pair rides only a guarded route of the target ---------------------------------------------------


@pytest.mark.parametrize("which", sorted(BUILDERS))
def test_a_read_carries_no_operator_pair_and_the_perimeter_secret(key_file, monkeypatch, which):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    rec = Recorder()
    client = route(BUILDERS[which](), rec)
    client.get("/tokens")
    client.get("/heartbeat/a1")
    for req in rec.requests:
        assert not [h for h in OP_HEADERS if h in req.headers], req.url
        assert req.headers[authn.HEADER] == SECRET


@pytest.mark.parametrize("which", sorted(BUILDERS))
def test_every_guarded_route_of_the_target_carries_the_pair(key_file, monkeypatch, which):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    templates = {"delegation": go.DELEGATION_TEMPLATES, "killswitch": go.KILLSWITCH_TEMPLATES}[which]
    rec = Recorder()
    client = route(BUILDERS[which](), rec)
    for method, template in templates:
        client.request(method, re.sub(r"\{[^/}]+\}", "x1", template))
        assert rec.last_operator_pair() == (OPERATOR, KEY_OLD), (method, template)
    assert len(rec.requests) == len(templates)


def test_a_route_of_the_other_target_carries_no_pair(key_file):
    rec = Recorder()
    client = route(delegation_client(), rec)
    client.post("/kill/a1")                                     # a kill-switch route sent to delegation
    assert rec.last_operator_pair() == (None, None)


def test_a_client_built_without_a_table_sends_the_perimeter_secret_only(key_file, monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    rec = Recorder()
    client = route(api_module.PerRequestAuthClient(base_url="http://delegation.invalid"), rec)
    client.post("/tokens/t-1/revoke")
    assert rec.last_operator_pair() == (None, None)
    assert rec.requests[0].headers[authn.HEADER] == SECRET


def test_an_absolute_url_elsewhere_and_under_a_base_prefix(key_file, monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    rec = Recorder()
    client = route(api_module.PerRequestAuthClient(base_url="http://delegation.invalid/da",
                                                   guarded_routes=go.DELEGATION_GUARDED), rec)
    client.post("/tokens/t-1/revoke")                           # relative: under the base
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)
    client.post("http://delegation.invalid/da/tokens/t-1/revoke")
    assert rec.last_operator_pair() == (OPERATOR, KEY_OLD)
    client.post("http://other.invalid/da/tokens/t-1/revoke")    # another origin: NO credential at all (C-586 F-3)
    assert rec.last_operator_pair() == (None, None)
    assert authn.HEADER not in rec.requests[-1].headers
    client.post("http://delegation.invalid:9999/da/tokens/t-1/revoke")      # another port is another origin
    assert authn.HEADER not in rec.requests[-1].headers and rec.last_operator_pair() == (None, None)
    client.post("https://delegation.invalid/da/tokens/t-1/revoke")          # another scheme too
    assert authn.HEADER not in rec.requests[-1].headers and rec.last_operator_pair() == (None, None)
    client.post("http://delegation.invalid/elsewhere/tokens/t-1/revoke")    # same origin, outside the prefix
    assert rec.last_operator_pair() == (None, None) and rec.requests[-1].headers[authn.HEADER] == SECRET


# --- C-586: the constructor pins trust_env and follow_redirects; a proxy and a redirect get nothing -----------------


@pytest.mark.parametrize("which", sorted(BUILDERS))
def test_an_explicit_trust_env_or_follow_redirects_cannot_turn_either_on(which):
    client = BUILDERS[which]()
    assert client.trust_env is False and client.follow_redirects is False
    forced = api_module.PerRequestAuthClient(trust_env=True, follow_redirects=True, guarded_routes=go.DELEGATION_GUARDED)
    assert forced.trust_env is False and forced.follow_redirects is False


def test_a_proxy_in_the_environment_gets_no_hit_from_a_client_with_a_route_table(key_file, monkeypatch):
    import socket
    import threading

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    listener.settimeout(0.2)
    hits: list[int] = []
    stop = threading.Event()

    def accept():
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except (socket.timeout, OSError):
                continue
            hits.append(1)
            conn.close()

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    try:
        for var in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(var, f"http://127.0.0.1:{listener.getsockname()[1]}")
        monkeypatch.setenv(authn.ENV_VAR, SECRET)
        client = api_module.PerRequestAuthClient(base_url="http://delegation.invalid", timeout=2.0,
                                                 guarded_routes=go.DELEGATION_GUARDED)
        for method, path in (("POST", "/tokens/t-1/revoke"), ("GET", "/tokens")):
            with pytest.raises(httpx.HTTPError):               # nothing listens at the target: it must fail to connect
                client.request(method, path)
        assert hits == []
    finally:
        stop.set()
        thread.join(timeout=2)
        listener.close()


@pytest.mark.parametrize("which", sorted(BUILDERS))
def test_a_redirect_is_not_followed_and_nothing_reaches_the_target_of_it(key_file, monkeypatch, which):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "http://elsewhere.invalid/x"}, request=request)

    client = BUILDERS[which]()
    client._transport = httpx.MockTransport(handler)
    client._mounts = {}
    method, path = GUARDED[which]
    resp = client.request(method, path)
    assert resp.status_code == 302 and len(seen) == 1
    assert seen[0].url.host != "elsewhere.invalid"
    assert client.get("/tokens", follow_redirects=False).status_code == 302


def test_no_call_path_can_make_the_client_follow_a_redirect(key_file, monkeypatch):
    # C-592 (reviewer C-569 F-C569-1): the construction pin is not enough; per-call and later-assignment opt-ins too
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    for how in ("get", "request", "send", "attribute", "stream"):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://elsewhere.invalid/x"}, request=request)

        client = api_module.PerRequestAuthClient(transport=httpx.MockTransport(handler))
        url = "http://registry.invalid/tokens"
        if how == "get":
            resp = client.get(url, follow_redirects=True)
        elif how == "request":
            resp = client.request("GET", url, follow_redirects=True)
        elif how == "send":
            resp = client.send(client.build_request("GET", url), follow_redirects=True)
        elif how == "attribute":
            client.follow_redirects = True
            resp = client.get(url)
        else:
            with client.stream("GET", url, follow_redirects=True) as resp:
                resp.read()
        assert resp.status_code == 302, how
        assert seen == [url], (how, seen)


# --- C-660 (reviewer C-624): the pair is decided on the path httpx puts on the wire ---------------------------------


def _wire(client_kw, method, url):
    """Send one request through a recorder; (wire path, operator pair, perimeter secret)."""
    rec = Recorder()
    client = route(api_module.PerRequestAuthClient(**client_kw), rec)
    client.request(method, url)
    req = rec.requests[-1]
    return req.url.path, rec.last_operator_pair(), req.headers.get(authn.HEADER)


@pytest.mark.parametrize("url,wire_path,carries_pair", [
    ("/tokens/../tokens", "/tokens", True),                      # a guarded write that the raw string hid
    ("/tokens/t-1/../t-2/revoke", "/tokens/t-2/revoke", True),
    ("/tokens/./t-1/revoke", "/tokens/t-1/revoke", True),
    ("/tokens/../revoke", "/revoke", False),                     # raw string looked like .../revoke: not a route on the wire
    ("../health/revoke", "/health/revoke", False),
    # an id of ".." the receiver (Starlette) routes to /tokens/{token_id}/revoke, so it IS the guarded route (C-731
    # F-C731-5). field-core's RegistryClient decides the other way for an encoded dot id (no pair: fail closed); both safe.
    ("/tokens/%2e%2e/revoke", "/tokens/../revoke", True),
    ("/tokens/%2E%2E/revoke", "/tokens/../revoke", True),
    ("/tokens/a%2Fb/revoke", "/tokens/a/b/revoke", False),       # an encoded slash is two segments to the receiver
])
def test_the_pair_follows_the_wire_path_not_the_callers_string(key_file, monkeypatch, url, wire_path, carries_pair):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    got_path, pair, secret = _wire({"base_url": "http://delegation.invalid", "guarded_routes": go.DELEGATION_GUARDED},
                                   "POST", url)
    assert got_path == wire_path
    assert (pair == (OPERATOR, KEY_OLD)) is carries_pair, (url, got_path, pair)
    assert secret == SECRET


def test_the_wire_path_decides_under_a_base_prefix_too(key_file, monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    kw = {"base_url": "http://delegation.invalid/da", "guarded_routes": go.DELEGATION_GUARDED}
    assert _wire(kw, "POST", "/tokens/../tokens")[1] == (OPERATOR, KEY_OLD)       # /da/tokens
    path, pair, secret = _wire(kw, "POST", "/tokens/../../elsewhere/tokens")       # leaves the base path
    assert path == "/elsewhere/tokens" and pair == (None, None) and secret == SECRET


def test_a_trailing_slash_and_an_absolute_url_outside_the_base_path_get_no_pair(key_file, monkeypatch):
    """C-731 F-C731-4: ``/tokens/`` is not the route (the receiver would answer a redirect, which is never followed),
    and an absolute same-origin URL outside the base path gets the secret only, even where its path is a route."""
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    kw = {"base_url": "http://delegation.invalid/da", "guarded_routes": go.DELEGATION_GUARDED}
    assert _wire(kw, "POST", "/tokens/")[1] == (None, None)
    path, pair, secret = _wire(kw, "POST", "http://delegation.invalid/tokens")
    assert path == "/tokens" and pair == (None, None) and secret == SECRET


def test_a_foreign_prefix_of_the_same_length_as_the_base_path_gets_no_pair(key_file, monkeypatch):
    """C-731 F-C731-3: base ``/da`` and absolute path ``/ab/tokens/t-1/revoke`` slice to a guarded route; it is outside the base."""
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    kw = {"base_url": "http://delegation.invalid/da", "guarded_routes": go.DELEGATION_GUARDED}
    path, pair, secret = _wire(kw, "POST", "http://delegation.invalid/ab/tokens/t-1/revoke")
    assert path == "/ab/tokens/t-1/revoke" and pair == (None, None) and secret == SECRET


def test_the_client_class_defines_each_method_once():
    """A merge of PR 318 and PR 330 without the comms merge-fix patch leaves a second ``__init__`` and ``send`` that
    git does not flag (C-731): the later one wins silently, so the earlier is dead code. Fail loudly instead."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(api_module))
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "PerRequestAuthClient")
    names = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
    dup = sorted({n for n in names if names.count(n) > 1})
    assert not dup, f"PerRequestAuthClient defines {dup} more than once"


def test_a_method_in_lower_case_still_carries_the_pair_on_a_guarded_write(key_file, monkeypatch):
    # C-586 F-C586-2 / C-624: the table compares the method case-insensitively
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    kw = {"base_url": "http://delegation.invalid", "guarded_routes": go.DELEGATION_GUARDED}
    for method in ("post", "Post", "POST"):
        assert _wire(kw, method, "/tokens/t-1/revoke")[1] == (OPERATOR, KEY_OLD), method
    assert _wire(kw, "get", "/tokens/t-1/revoke")[1] == (None, None)


def test_a_relative_path_without_a_leading_slash_is_the_same_route(key_file):
    # no base URL: httpx leaves the URL relative, so the client itself must add the slash (C-624 NEW LOW)
    client = api_module.PerRequestAuthClient(guarded_routes=go.DELEGATION_GUARDED)
    assert client.build_request("POST", "tokens/t-1/revoke").headers.get(oa.HEADER_OPERATOR) == OPERATOR
    assert client.build_request("GET", "tokens/t-1").headers.get(oa.HEADER_OPERATOR) is None
    with_base = api_module.PerRequestAuthClient(base_url="http://delegation.invalid/da", guarded_routes=go.DELEGATION_GUARDED)
    assert with_base.build_request("POST", "tokens/t-1/revoke").headers.get(oa.HEADER_OPERATOR) == OPERATOR
