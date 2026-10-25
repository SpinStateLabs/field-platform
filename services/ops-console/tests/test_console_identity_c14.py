"""Phase G C-14 (design RT1-5): the ops-console never acts under an operator
identity of its own.

Before C-14 the console's upstream clients were built with ``auth_headers()``,
which includes ``operator_headers()``; with ``FIELD_OPERATOR`` set console-side
a human action that arrived WITHOUT the human's headers went downstream as the
console's identity. Pinned here:

* a ``ServiceClient`` the console builds carries ``x-field-auth`` only, and no
  ``x-field-operator*`` header ever leaves the console for a request that had
  none; a request that had the human's pair carries exactly that pair;
* the console refuses to START when ``FIELD_OPERATOR``, ``FIELD_OPERATOR_KEY``
  or ``FIELD_OPERATOR_KEY_FILE`` is set (non-blank): the app's lifespan fails
  (so any ASGI server refuses it) and ``console serve`` exits 2 before serving.
  The refusal names the variables, never their values.

Keys are generated per run and never printed.
"""

from __future__ import annotations

import hashlib
import secrets

import httpx
import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core.authn import ENV_VAR as SECRET_ENV, HEADER as SECRET_HEADER
from ops_console import api as console_api
from ops_console.api import ServiceClient, create_app

OWN = (oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_OPERATOR_KEY_FILE")
OPERATOR_HEADERS = {oa.HEADER_OPERATOR, oa.HEADER_KEY}
BODY = {"operator": "Don", "reason": "c14"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (*OWN, oa.ENV_REGISTRY, oa.ENV_REQUIRE, SECRET_ENV):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def wire(monkeypatch):
    """Every httpx.Client built from here on keeps its caller's arguments but
    talks to a recording transport."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/agents":
            return httpx.Response(200, json=[{"agent_id": "a1", "domain": "finance", "status": "active"}])
        return httpx.Response(200, json={"ok": True, "killed": [], "already_killed": [], "results": []})

    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return seen


def _fp(value):
    """Fingerprint only: a failing assertion prints this, never a key."""
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:8]


def _console_identity(monkeypatch):
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-console")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, secrets.token_urlsafe(24))


def _injected():
    class Rec:
        def get(self, path, **kw):
            raise ConnectionError("n/a")

        def post(self, path, **kw):
            raise ConnectionError("n/a")

    sc = lambda: ServiceClient(client=Rec(), base_url="http://t")  # noqa: E731
    return dict(registry=sc(), ledger=sc(), delegation=sc(), governor=sc(), killswitch=sc(),
                sentinel=sc(), lifecycle=sc(), attest=sc(), crosswalk=sc(), federation=sc(),
                replay=sc(), gateway=sc())


# ---- clients carry x-field-auth only ------------------------------------------------


def test_a_console_service_client_carries_x_field_auth_only(wire, monkeypatch):
    _console_identity(monkeypatch)                     # even if the env holds a pair
    monkeypatch.setenv(SECRET_ENV, "perimeter-c14")
    sc = ServiceClient(base_url="http://killswitch.test")
    assert {k.lower() for k in sc._client.headers} & OPERATOR_HEADERS == set()
    sc.post("/kill/a1", json=BODY)
    sc.get("/heartbeat/a1")
    assert len(wire) == 2
    for req in wire:
        assert req.headers.get(SECRET_HEADER) == "perimeter-c14"
        assert {k.lower() for k in req.headers} & OPERATOR_HEADERS == set()


@pytest.mark.parametrize("path,body", [
    ("/api/agents/a1/kill", BODY), ("/api/agents/a1/revive", BODY), ("/api/agents/a1/drill", BODY),
    ("/api/agents/bulk", {"agent_ids": ["a1"], "action": "kill", **BODY}),
    ("/api/fleet/halt", {"domains": ["finance"], "confirm": "HALT", **BODY}),
    ("/api/tokens/t1/revoke", None),
    ("/api/escalations/e1/resolve", {"resolved_by": "Don"}),
])
def test_no_operator_header_leaves_the_console_for_a_request_that_had_none(wire, monkeypatch, path, body):
    """The app built for real (every upstream client is the console's own),
    with a console-side pair in the environment that the startup check would
    refuse: a human action without headers goes downstream with none."""
    _console_identity(monkeypatch)
    monkeypatch.setenv(SECRET_ENV, "perimeter-c14")
    c = TestClient(create_app())                       # no lifespan: requests only
    auth = {SECRET_HEADER: "perimeter-c14"}
    r = c.post(path, json=body, headers=auth) if body is not None else c.post(path, headers=auth)
    assert r.status_code == 200, r.text
    assert wire, "nothing was proxied"
    for req in wire:
        assert {k.lower() for k in req.headers} & OPERATOR_HEADERS == set(), req.url.path


def test_a_human_pair_is_forwarded_exactly_and_the_console_pair_never(wire, monkeypatch):
    _console_identity(monkeypatch)
    human_key = secrets.token_urlsafe(24)
    c = TestClient(create_app())
    r = c.post("/api/agents/a1/kill", json=BODY,
               headers={oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: human_key})
    assert r.status_code == 200
    sent = wire[-1].headers
    assert sent.get(oa.HEADER_OPERATOR) == "don"
    assert _fp(sent.get(oa.HEADER_KEY)) == _fp(human_key)
    assert sent.get_list(oa.HEADER_OPERATOR) == ["don"]


# ---- refuse to start -----------------------------------------------------------------


@pytest.mark.parametrize("name", OWN)
def test_the_app_refuses_to_start_with_an_identity_of_its_own(monkeypatch, name):
    value = secrets.token_urlsafe(24)
    monkeypatch.setenv(name, value)
    app = create_app(**_injected())
    with pytest.raises(console_api.ConsoleIdentityRefused) as exc:
        with TestClient(app):
            pass
    assert name in str(exc.value) and value not in str(exc.value)


def test_the_refusal_holds_in_every_mode(monkeypatch):
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-console")
    for require in ("", "1"):
        monkeypatch.setenv(oa.ENV_REQUIRE, require)
        with pytest.raises(console_api.ConsoleIdentityRefused):
            with TestClient(create_app(**_injected())):
                pass


def test_blank_values_are_unset_and_the_console_starts(monkeypatch):
    for name in OWN:
        monkeypatch.setenv(name, "  ")
    with TestClient(create_app(**_injected())) as c:
        assert c.get("/health").json()["ok"] is True


def test_uvicorn_fails_startup_and_never_serves(monkeypatch):
    """A server started on the app object directly (not through ``console
    serve``) also refuses: uvicorn's startup fails before it binds a socket and
    the server never reports started. Bounded: a server that DID start is told
    to exit after a few seconds, so the failing case cannot hang the suite."""
    import threading

    import uvicorn

    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, secrets.token_urlsafe(24))
    server = uvicorn.Server(uvicorn.Config(create_app(**_injected()), host="127.0.0.1", port=0,
                                           log_config=None, log_level="critical"))
    stop = threading.Timer(8.0, lambda: setattr(server, "should_exit", True))
    stop.start()
    code = None
    try:
        server.run()
    except SystemExit as exc:          # uvicorn's startup-failure exit
        code = exc.code
    finally:
        stop.cancel()
    assert server.started is False and code == 3


@pytest.mark.parametrize("name", OWN)
def test_console_serve_exits_2_before_serving(monkeypatch, name):
    import uvicorn
    from typer.testing import CliRunner

    from ops_console.cli import app as cli

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: calls.append(k))
    value = secrets.token_urlsafe(24)
    monkeypatch.setenv(name, value)
    result = CliRunner().invoke(cli, ["serve", "--port", "1"])
    assert result.exit_code == 2 and calls == []
    assert name in result.output and value not in result.output


def test_console_serve_starts_without_an_identity(monkeypatch):
    import uvicorn
    from typer.testing import CliRunner

    from ops_console.cli import app as cli

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: calls.append(k))
    result = CliRunner().invoke(cli, ["serve", "--port", "1"])
    assert result.exit_code == 0, result.output
    assert calls == [{"host": "127.0.0.1", "port": 1}]
