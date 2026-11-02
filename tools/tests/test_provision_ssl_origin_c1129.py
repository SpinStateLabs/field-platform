"""provision_ssl_agents.py: the operator pair never leaves for another origin (C-1129, reviewer C-1119 F-C1119-2).

The tool's own guarded auth checked the (method, path) allowlist but not the origin, so a redirect or a URL built
from another host carried the pair when the path matched (field-core's GuardedOperatorAuth refuses that, C-731
F-C731-1). Asserted on the headers the auth leaves on a request, no network. Every value is a made-up test value."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

TOOLS = Path(__file__).resolve().parents[1]
PAIR = ("test-operator", "test-op-key-NEVER-PRINT-c1129-0123456789abcdef")
BASE = "http://proxy.test:9000"


@pytest.fixture()
def auth(monkeypatch):
    monkeypatch.setenv("FIELD_PROXY_URL", BASE)
    spec = importlib.util.spec_from_file_location("provision_ssl_agents_c1129", TOOLS / "provision_ssl_agents.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._GuardedOperatorAuth(PAIR)


def _headers(auth, method, url):
    request = httpx.Request(method, url)
    next(auth.auth_flow(request))
    return request.headers


def test_a_guarded_route_on_the_proxy_origin_carries_the_pair(auth):
    h = _headers(auth, "POST", f"{BASE}/registry/agents")
    assert h.get("x-field-operator") == PAIR[0] and h.get("x-field-operator-key") == PAIR[1]


@pytest.mark.parametrize("url", [
    "http://other.test:9000/registry/agents",       # another host
    "http://proxy.test:9001/registry/agents",       # another port
    "https://proxy.test:9000/registry/agents",      # another scheme
])
def test_a_guarded_route_on_another_origin_never_carries_the_pair(auth, url):
    h = _headers(auth, "POST", url)
    assert "x-field-operator" not in h and "x-field-operator-key" not in h
