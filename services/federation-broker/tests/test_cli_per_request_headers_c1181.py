"""C-1181 (Lane 7 C-1150 F2, slice C): the federation-broker CLI puts the operator pair only on the one guarded write.

Before this change every CLI request used ``auth_headers()``, so the env operator pair rode the contract list and the
crossing decision too. Now each request asks field-core's ``request_headers`` for its own headers: the perimeter secret
always, the pair only on ``PUT /contracts/{id}``. Values are made up; nothing leaves the process.
"""
from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from federation_broker import cli
from federation_broker.api import create_app
from field_core import authn
from field_core import operator_auth as oa
from field_core.guarded_operator import guard_dependent_routes

SECRET = "made-up-perimeter-secret"
OP, KEY = "made-up-operator", "fok_made-up-key-0123456789abcdef"
RUNNER = CliRunner()


@pytest.fixture()
def sent(monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    monkeypatch.setenv(oa.ENV_OPERATOR, OP)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY)
    monkeypatch.setenv("FIELD_FEDERATION_URL", "http://broker.invalid")
    seen: list[tuple[str, str, dict]] = []

    def make(method):
        def fake(url, **kw):
            seen.append((method, url.removeprefix("http://broker.invalid"), dict(kw.get("headers") or {})))
            return httpx.Response(200, json={"verdict": "ALLOW"}, request=httpx.Request(method, url))
        return fake
    for m in ("get", "put", "post"):
        monkeypatch.setattr(httpx, m, make(m.upper()))
    return seen


def _pair(headers: dict) -> bool:
    return oa.HEADER_OPERATOR in headers or oa.HEADER_KEY in headers


def test_the_contract_write_carries_the_pair_and_nothing_else_does(sent, tmp_path):
    manifest = tmp_path / "m.yaml"
    manifest.write_text("agent_id: a\n", encoding="utf-8")
    RUNNER.invoke(cli.app, ["add-contract", "c-1", "--org", "o", "--scope", "s", "--data-class", "d"])
    RUNNER.invoke(cli.app, ["contracts"])
    RUNNER.invoke(cli.app, ["crossing", "--org", "o", "--agent-id", "a", "--manifest", str(manifest),
                            "--scope", "s", "--data-class", "d", "--direction", "outbound"])
    by = {(m, p): h for m, p, h in sent}
    assert set(by) == {("PUT", "/contracts/c-1"), ("GET", "/contracts"), ("POST", "/crossing")}, sorted(by)
    for (m, p), h in by.items():
        assert h.get(authn.HEADER) == SECRET, (m, p)                           # the perimeter secret always
        assert _pair(h) is (m == "PUT"), (m, p, sorted(h))                     # the pair only on the guarded write
    assert by[("PUT", "/contracts/c-1")][oa.HEADER_OPERATOR] == OP


def test_the_cli_table_equals_the_routes_the_broker_guards():
    assert set(cli.FEDERATION_TEMPLATES) == guard_dependent_routes(create_app())
