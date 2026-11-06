"""C-1179 (Lane 7 C-1150 F2, slice A): the spend-governor CLI puts the operator pair only on a guarded write.

Before this change every CLI request used ``auth_headers()``, so the env operator pair rode every request, reads and
the agent-reported ``/spend`` and ``/usage`` included. Now each request asks field-core's ``request_headers`` for its own
headers: the perimeter secret always, the pair only on a route in ``GOVERNOR_GUARDED``. Every value is made up; no
request leaves the process (httpx's module functions are replaced by recorders).
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from field_core import authn
from field_core import operator_auth as oa
from field_core.guarded_operator import guard_dependent_routes
from spend_governor import cli
from spend_governor.api import create_app
from spend_governor.core import GovernorStore

SECRET = "made-up-perimeter-secret"
OP, KEY = "made-up-operator", "fok_made-up-key-0123456789abcdef"
MANIFEST = Path(__file__).resolve().parents[3] / "manifests" / "canary-gb10.yaml"
RUNNER = CliRunner()


@pytest.fixture()
def sent(monkeypatch):
    """Record (method, path, headers) of every request the CLI sends."""
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    monkeypatch.setenv(oa.ENV_OPERATOR, OP)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY)
    monkeypatch.setenv("FIELD_GOVERNOR_URL", "http://governor.invalid")
    seen: list[tuple[str, str, dict]] = []

    def make(method: str):
        def fake(url, **kw):
            path = url.removeprefix("http://governor.invalid")
            seen.append((method, path, dict(kw.get("headers") or {})))
            body = {"state": "OK", "rate_limits": [], "rogue": False}
            status = 201 if method == "POST" and path in ("/spend", "/usage") else 200
            return httpx.Response(status, json=body, request=httpx.Request(method, url))
        return fake
    for m in ("get", "put", "post"):
        monkeypatch.setattr(httpx, m, make(m.upper()))
    return seen


def _pair(headers: dict) -> bool:
    return oa.HEADER_OPERATOR in headers or oa.HEADER_KEY in headers


# command line, then the (method, path) requests it must send and whether each is a guarded write
CASES = [
    (["set-cap", "agent-a", "--limit-cents", "100"], [("PUT", "/caps/agent-a", True)]),
    (["spend", "agent-a", "--cents", "5"], [("POST", "/spend", False)]),
    (["rate-limits", "agent-a"], [("GET", "/rate-limits/agent-a", False)]),
    (["status", "agent-a"], [("GET", "/status/agent-a", False)]),
    (["usage", "agent-a"], [("GET", "/usage/agent-a", False)]),
    (["usage", "agent-a", "--model", "m", "--in", "1"], [("POST", "/usage", False)]),
    (["set-policy", "agent-a"], [("PUT", "/policies/agent-a", True)]),
    (["escalations"], [("GET", "/escalations", False)]),
    (["resolve", "esc-1", "--by", "don"], [("POST", "/escalations/esc-1/resolve", True)]),
]


@pytest.mark.parametrize("argv,expected", CASES, ids=[" ".join(c[0][:2]) for c in CASES])
def test_the_pair_rides_only_a_guarded_write_and_the_secret_rides_every_request(sent, argv, expected):
    RUNNER.invoke(cli.app, argv)
    assert [(m, p) for m, p, _ in sent] == [(m, p) for m, p, _ in expected], sent
    for (method, path, guarded), (_, _, headers) in zip(expected, sent):
        assert headers.get(authn.HEADER) == SECRET, (method, path)             # the perimeter secret always
        assert _pair(headers) is guarded, (method, path, sorted(headers))      # the pair only on a guarded write
        if guarded:
            assert headers[oa.HEADER_OPERATOR] == OP and headers[oa.HEADER_KEY] == KEY


def test_the_rate_limit_loader_reads_without_the_pair_and_writes_with_it(sent):
    RUNNER.invoke(cli.app, ["set-cap", "canary-gb10", "--from-manifest", str(MANIFEST)])
    by = {(m, p): h for m, p, h in sent}
    assert ("PUT", "/caps/canary-gb10") in by and any(p.startswith("/rate-limits/") for _, p in by), sorted(by)
    for (m, p), h in by.items():
        assert _pair(h) is (m == "PUT"), (m, p, sorted(h))


def test_the_cli_table_equals_the_routes_the_governor_guards(tmp_path):
    app = create_app(store=GovernorStore(tmp_path / "g.sqlite3"))
    assert set(cli.GOVERNOR_TEMPLATES) == guard_dependent_routes(app)


def test_the_rate_limit_loader_get_carries_no_pair_when_no_limits_are_declared(sent):
    # a manifest with a spend cap and NO rate_limits: the loader reads the current set first (a GET), then stops
    NO_LIMITS = MANIFEST.with_name("conformance-sentinel.yaml")
    RUNNER.invoke(cli.app, ["set-cap", "conformance-sentinel", "--from-manifest", str(NO_LIMITS)])
    gets = [(p, h) for m, p, h in sent if m == "GET" and p.startswith("/rate-limits/")]
    assert gets, sent                                                          # the GET really happened
    for p, h in gets:
        assert authn.HEADER in h and not _pair(h), (p, sorted(h))
