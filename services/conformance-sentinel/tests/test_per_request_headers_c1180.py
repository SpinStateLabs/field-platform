"""C-1180 (reviewer C-1150 F2, slice B): conformance-sentinel's outbound clients carry the operator pair only on a
guarded write.

``auth_headers()`` merges the service's own operator pair (``x-field-operator``, ``x-field-operator-key``) into every
request a client sends, reads included, to receivers that check the pair only on guarded writes. The sentinel's own
routes carry no operator guard, so a client talking to the sentinel, the governor or the delegation introspection
needs the perimeter secret and nothing else; the registry and delegation clients the measurement CLI provisions
through need the pair on ``POST /agents`` and ``POST /tokens`` and nowhere else. Every id and key here is made up."""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from field_core import operator_auth as oa
from field_core.guarded_operator import DELEGATION_GUARDED, REGISTRY_GUARDED

SRC = Path(__file__).resolve().parents[1] / "src" / "conformance_sentinel"
PAIR = ("svc-made-up", "made-up-operator-key-0123456789")
SECRET = "made-up-shared-secret-0123456789"


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    monkeypatch.setenv(oa.ENV_OPERATOR, PAIR[0])
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, PAIR[1])
    monkeypatch.delenv(oa.ENV_OPERATOR_KEY_FILE, raising=False)


def _pairless(headers) -> bool:
    return oa.HEADER_OPERATOR not in headers and oa.HEADER_KEY not in headers and headers.get("x-field-auth") == SECRET


# ---- the three clients that build their own httpx.Client (engine, governed): the default headers carry no pair ----

def test_the_governor_status_client_carries_the_perimeter_secret_and_no_pair():
    from conformance_sentinel.engine import SpendStatusClient
    assert _pairless(SpendStatusClient()._client.headers)


def test_the_delegation_introspect_client_carries_the_perimeter_secret_and_no_pair():
    from conformance_sentinel.engine import DelegationIntrospectClient
    assert _pairless(DelegationIntrospectClient()._client.headers)


def test_the_governed_wrapper_client_carries_the_perimeter_secret_and_no_pair():
    from conformance_sentinel.governed import Governor
    assert _pairless(Governor("made-up-agent")._client.headers)


# ---- the measurement CLI's clients (headers.py has no typer, so these run wherever the sentinel does) -------------

def _capture(client_factory, method, path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.headers))
        return httpx.Response(200, json={})

    base = "http://registry.invalid:8001"
    with client_factory(base, httpx.MockTransport(handler)) as client:
        client.request(method, path)
    return seen


def test_the_sentinel_client_never_carries_the_pair():
    from conformance_sentinel import headers
    for method, path in (("GET", "/health"), ("POST", "/check")):
        seen = _capture(lambda b, t: headers.sentinel_client(b, transport=t), method, path)
        assert oa.HEADER_OPERATOR not in seen and seen.get("x-field-auth") == SECRET


@pytest.mark.parametrize("method,path,guarded", [
    ("GET", "/agents/made-up", False), ("GET", "/agents", False), ("POST", "/agents", True),
    ("POST", "/agents/made-up/attest", True),
])
def test_the_registry_client_carries_the_pair_on_a_guarded_write_only(method, path, guarded):
    from conformance_sentinel import headers
    seen = _capture(lambda b, t: headers.registry_client(b, transport=t), method, path)
    assert (oa.HEADER_OPERATOR in seen) is guarded
    assert seen.get("x-field-auth") == SECRET
    if guarded:
        assert seen[oa.HEADER_OPERATOR] == PAIR[0] and seen[oa.HEADER_KEY] == PAIR[1]


@pytest.mark.parametrize("method,path,guarded", [
    ("GET", "/tokens", False), ("POST", "/introspect", False), ("POST", "/tokens", True),
    ("POST", "/tokens/made-up/revoke", True),
])
def test_the_delegation_client_carries_the_pair_on_a_guarded_write_only(method, path, guarded):
    from conformance_sentinel import headers
    seen = _capture(lambda b, t: headers.delegation_client(b, transport=t), method, path)
    assert (oa.HEADER_OPERATOR in seen) is guarded
    assert seen.get("x-field-auth") == SECRET


def test_a_foreign_origin_never_gets_the_pair_even_on_a_guarded_path():
    """GuardedOperatorAuth is bound to its base: the same path on another host carries no pair."""
    from conformance_sentinel import headers
    seen = {}

    def handler(request):
        seen.update(dict(request.headers))
        return httpx.Response(200, json={})

    with headers.registry_client("http://registry.invalid:8001", transport=httpx.MockTransport(handler)) as c:
        c.post("http://other.invalid:9999/agents")
    assert oa.HEADER_OPERATOR not in seen


def test_the_tables_the_clients_use_are_the_receivers_own():
    from conformance_sentinel import headers
    assert headers.REGISTRY_TABLE is REGISTRY_GUARDED and headers.DELEGATION_TABLE is DELEGATION_GUARDED


# ---- no module of the service builds a client from auth_headers() any more -------------------------------------------


@pytest.mark.parametrize("module", ["cli.py", "engine.py", "governed.py"])
def test_no_module_passes_auth_headers_to_a_client(module):
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "auth_headers" not in names and "auth_headers" not in imports, module
