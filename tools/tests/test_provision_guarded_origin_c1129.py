"""C-1129 (cb19 seam audit, Lane 15 C-1119 F-C1119-2): ``provision_ssl_agents._GuardedOperatorAuth`` never gives the
operator pair to another origin.

The class decided on the request's PATH alone, so a request to any other host, port or scheme whose path matched a
guarded route carried the pair. field-core's ``GuardedOperatorAuth`` (C-731 F-C731-1) and the lifecycle CLI's copy
(C-944 F-C944-3) already refuse another origin; this pins the same rule here. Probe: an httpx request built by hand
(nothing is sent), made-up pair values, a made-up proxy base. Kill: drop the origin test from ``auth_flow``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import provision_ssl_agents as tool  # noqa: E402

BASE = "https://proxy.example.test:8443"
PAIR = ("c1129-made-up-operator", "c1129-made-up-key")
GUARDED_PATH = "/registry/agents"


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setattr(tool, "PROXY", BASE)


def _headers(url: str, method: str = "POST") -> httpx.Headers:
    request = httpx.Request(method, url)
    next(tool._GuardedOperatorAuth(PAIR).auth_flow(request))
    return request.headers


def test_the_pair_goes_to_a_guarded_route_on_the_base_origin():
    headers = _headers(BASE + GUARDED_PATH)
    assert headers.get("x-field-operator") == PAIR[0] and headers.get("x-field-operator-key") == PAIR[1]


@pytest.mark.parametrize("foreign", [
    "https://other.example.test:8443",      # another host
    "https://proxy.example.test:9443",      # another port
    "http://proxy.example.test:8443",       # another scheme
    "https://proxy.example.test.evil.test:8443",
])
def test_another_origin_never_gets_the_pair_whatever_its_path(foreign):
    headers = _headers(foreign + GUARDED_PATH)
    assert "x-field-operator" not in headers and "x-field-operator-key" not in headers


def test_an_unguarded_route_on_the_base_origin_still_gets_no_pair():
    headers = _headers(BASE + "/registry/agents/some-agent/heartbeat")
    assert "x-field-operator" not in headers
