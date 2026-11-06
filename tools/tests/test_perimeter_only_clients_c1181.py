"""C-1181 (Lane 7 C-1150 F2, slice C): clients that only read, or call unguarded routes, send the perimeter secret alone.

Ten code sites built a client with ``headers=auth_headers()``, so the env operator pair (FIELD_OPERATOR and its key) rode every
request: incident-replay (4), compliance-crosswalk (2), force-gateway (3), attestation-reporter (1). None of them calls a guarded
route (the targets are ledger, registry, delegation and sentinel reads, the governor's /usage /spend /status, and the
service's own unguarded routes), so each now uses ``perimeter_headers()``. Values are made up; no request leaves the process.
"""
from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from field_core import authn
from field_core import operator_auth as oa

REPO = Path(__file__).resolve().parents[2]
SECRET = "made-up-perimeter-secret"
OP, KEY = "made-up-operator", "fok_made-up-key-0123456789abcdef"
RUNNER = CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    monkeypatch.setenv(oa.ENV_OPERATOR, OP)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY)


def _perimeter_only(headers) -> bool:
    h = {k.lower(): v for k, v in dict(headers or {}).items()}
    return h.get(authn.HEADER) == SECRET and oa.HEADER_OPERATOR not in h and oa.HEADER_KEY not in h


@pytest.fixture()
def client_headers(monkeypatch):
    """Record the ``headers`` of every httpx.Client built."""
    seen: list[dict] = []
    real = httpx.Client

    def make(*a, **k):
        seen.append(dict(k.get("headers") or {}))
        return real(*a, **k)
    monkeypatch.setattr(httpx, "Client", make)
    return seen


def test_incident_replay_ledger_and_delegation_query_clients(client_headers):
    from incident_replay import engine
    engine.LedgerQueryClient(base_url="http://x.invalid")
    engine.TokenQueryClient(base_url="http://y.invalid")
    assert len(client_headers) == 2 and all(_perimeter_only(h) for h in client_headers), client_headers


def test_force_gateway_sentinel_client(client_headers):
    from force_gateway.api import SentinelClient
    SentinelClient(base_url="http://x.invalid")
    assert len(client_headers) == 1 and _perimeter_only(client_headers[0]), client_headers


def test_attestation_reporter_engine_clients(client_headers):
    from attestation_reporter.api import engine_from_env
    engine_from_env()
    assert client_headers and all(_perimeter_only(h) for h in client_headers), client_headers


def _record_module_calls(monkeypatch):
    seen: list[dict] = []

    def fake(method):
        def call(url, **kw):
            seen.append(dict(kw.get("headers") or {}))
            return httpx.Response(200, json={}, request=httpx.Request(method, url))
        return call
    for m in ("get", "post"):
        monkeypatch.setattr(httpx, m, fake(m.upper()))
    return seen


def test_incident_replay_cli_replay_both_forms(monkeypatch, tmp_path):
    from incident_replay import cli
    seen = _record_module_calls(monkeypatch)
    monkeypatch.setenv("FIELD_REPLAY_URL", "http://replay.invalid")
    base = ["run", "agent-a", "--since", "2026-01-01T00:00:00Z", "--until", "2026-01-02T00:00:00Z"]
    RUNNER.invoke(cli.app, base)
    RUNNER.invoke(cli.app, base + ["--markdown", str(tmp_path / "pm.md")])
    assert len(seen) == 2 and all(_perimeter_only(h) for h in seen), seen


def test_force_gateway_cli_telemetry(monkeypatch):
    from force_gateway import cli
    seen = _record_module_calls(monkeypatch)
    RUNNER.invoke(cli.app, ["telemetry"])
    assert len(seen) == 1 and _perimeter_only(seen[0]), seen


@pytest.mark.parametrize("rel", [
    "services/incident-replay/src/incident_replay/cli.py",
    "services/incident-replay/src/incident_replay/engine.py",
    "services/compliance-crosswalk/src/compliance_crosswalk/cli.py",
    "services/compliance-crosswalk/src/compliance_crosswalk/api.py",
    "services/force-gateway/src/force_gateway/cli.py",
    "services/force-gateway/src/force_gateway/api.py",
    "services/attestation-reporter/src/attestation_reporter/api.py",
])
def test_none_of_the_ten_sites_calls_auth_headers_any_more(rel):
    """The two crosswalk sites sit behind a live-platform branch no unit test reaches, so the whole set is also pinned
    by reading the syntax tree: no call to ``auth_headers`` (a name in a comment or docstring is not a call)."""
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    calls = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
             and (getattr(n.func, "id", None) == "auth_headers" or getattr(n.func, "attr", None) == "auth_headers")]
    assert not calls, (rel, calls)
