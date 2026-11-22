"""C-1181 (Lane 7 C-1150 F2, slice C part 4): two more sites send the perimeter secret alone.

``field_core.llm.anthropic_headers`` (a platform caller's Messages call, routed to the force-gateway) and claude-approver's
``Estate.headers()`` for an estate without its own secret file used ``auth_headers()``, so the env operator pair rode every
request. The gateway's ``/v1/messages`` and the approver's calls (sentinel ``POST /check``, kill-switch ``POST /heartbeat/{id}``,
governor ``POST /usage``) are not guarded routes, so both now use ``perimeter_headers()``. Values are made up.
"""
from __future__ import annotations

import pytest

from field_core import authn
from field_core import operator_auth as oa

SECRET = "made-up-perimeter-secret"
OP, KEY = "made-up-operator", "fok_made-up-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    monkeypatch.setenv(oa.ENV_OPERATOR, OP)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY)


def _perimeter_only(headers) -> bool:
    h = {k.lower(): v for k, v in dict(headers or {}).items()}
    return h.get(authn.HEADER) == SECRET and oa.HEADER_OPERATOR not in h and oa.HEADER_KEY not in h


def test_anthropic_headers_via_the_gateway_carry_the_secret_and_no_operator_pair(monkeypatch):
    from field_core import llm
    monkeypatch.setenv(llm.GATEWAY_URL_ENV, "http://gateway.invalid")
    headers = llm.anthropic_headers("made-up-api-key")
    assert llm.PASSTHROUGH_HEADER in headers                                  # it really took the gateway branch
    assert _perimeter_only(headers), sorted(headers)


def test_anthropic_headers_without_the_gateway_carry_no_platform_header(monkeypatch):
    from field_core import llm
    monkeypatch.delenv(llm.GATEWAY_URL_ENV, raising=False)
    headers = llm.anthropic_headers("made-up-api-key")
    assert authn.HEADER not in headers and oa.HEADER_OPERATOR not in headers


def test_a_claude_approver_estate_without_its_own_secret_file_sends_the_secret_alone():
    from claude_approver.core import Estate
    estate = Estate("http://s.invalid", "http://k.invalid", "http://g.invalid", False)
    assert _perimeter_only(estate.headers()), estate.headers()
