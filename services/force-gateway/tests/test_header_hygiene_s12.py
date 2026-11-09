"""S12-28: the /v1/messages edge is hygienic about what it echoes and what it forwards.

(1) A refused call (503, the sentinel check did not happen) carried `sentinel unreachable at <URL>: <Class>: <transport
    text>`: the internal sentinel URL and the exception text, to the caller. The body now names only a fixed category.
(2) `anthropic-version` was forwarded as any caller string to the upstream with the real x-api-key. It must be a date;
    a non-ASCII value would raise UnicodeEncodeError inside httpx (measured: it does) and become a 500.
(3) x-field-agent-id, x-field-token and x-field-action go into the sentinel body and the gateway.refused ledger payload:
    1..128 characters, one line, no control characters, else a 422 with fixed text."""
from __future__ import annotations

import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from field_core.llm import EGRESS_ACTION
from force_gateway.api import SentinelClient, SentinelUnavailable, create_app, real_upstream

MSG = {"model": "m", "max_tokens": 16, "messages": [{"role": "user", "content": "ping"}]}
GOOD = {"x-field-agent-id": "invoicing-agent", "x-field-token": "tok-1"}
INTERNAL = "http://internal-sentinel.corp.example:9443/prefix"


class Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, body, headers):
        self.calls.append(dict(headers))
        return 200, {"id": "x", "type": "message", "role": "assistant", "model": "m", "content": [], "stop_reason": "end_turn",
                     "usage": {"input_tokens": 1, "output_tokens": 1}}


class AllowSentinel:
    base_url = "http://t"

    def __init__(self):
        self.seen = []

    def check(self, agent_id, token_id, action):
        self.seen.append((agent_id, token_id, action))
        return {"decision": "ALLOW", "clause_id": None, "reasons": [], "context": {}}


class Boom:
    """An httpx-like client whose transport fails with text that names internal hosts."""

    def post(self, url, **kw):
        raise httpx.ConnectError("connection refused to internal-sentinel.corp.example:9443 (secret-detail-77)")


def _app(sentinel, *, enforce=True):
    spy = Spy()
    return TestClient(create_app(upstream=spy, sentinel_client=sentinel, enforce=enforce, sample_every=0)), spy


# ---- (1) the 503 body --------------------------------------------------------------------------------------------------

def test_an_unreachable_sentinel_503_never_shows_the_url_or_the_transport_text(caplog):
    caplog.set_level(logging.WARNING, logger="force_gateway")
    client, spy = _app(SentinelClient(client=Boom(), base_url=INTERNAL))
    r = client.post("/v1/messages", json=MSG, headers=GOOD)
    assert r.status_code == 503 and spy.calls == []
    detail = r.json()["detail"]
    assert detail == "sentinel check did not happen — refusing: sentinel unreachable"
    for leak in ("internal-sentinel", "corp.example", "9443", "secret-detail-77", "ConnectError", "prefix"):
        assert leak not in r.text
    # the log keeps the exception CLASS, not its text or the URL
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert "ConnectError" in logged
    for leak in ("internal-sentinel", "corp.example", "secret-detail-77"):
        assert leak not in logged


class _Status:
    def __init__(self, code, body=None):
        self.code, self.body = code, body

    def post(self, url, **kw):
        outer = self

        class Resp:
            status_code = outer.code

            def json(_):
                if isinstance(outer.body, Exception):
                    raise outer.body
                return outer.body
        return Resp()


@pytest.mark.parametrize("sentinel_client,expected", [
    (_Status(500, {"detail": "boom"}), "sentinel returned 500"),
    (_Status(503), "sentinel returned 503"),
    (_Status(200, ValueError("not json")), "sentinel returned a non-JSON body"),
    (_Status(200, {"ok": True}), "sentinel returned no verdict"),
])
def test_the_other_failure_categories_keep_their_fixed_wording(sentinel_client, expected):
    client, spy = _app(SentinelClient(client=sentinel_client, base_url=INTERNAL))
    r = client.post("/v1/messages", json=MSG, headers=GOOD)
    assert r.status_code == 503 and spy.calls == []
    assert r.json()["detail"] == f"sentinel check did not happen — refusing: {expected}"
    assert "internal-sentinel" not in r.text


def test_an_unknown_sentinel_failure_text_is_a_generic_category_not_an_echo():
    class Odd:
        base_url = "http://t"

        def check(self, *a):
            raise SentinelUnavailable("something at http://leak.example/x with SECRET-ODD")
    client, _ = _app(Odd())
    r = client.post("/v1/messages", json=MSG, headers=GOOD)
    assert r.status_code == 503
    assert r.json()["detail"] == "sentinel check did not happen — refusing: sentinel check failed"
    assert "SECRET-ODD" not in r.text and "leak.example" not in r.text


@pytest.mark.parametrize("message", ["sentinel returned SECRET-ODD", "sentinel returned 5000", "sentinel returned 50",
                                     "sentinel returned 500 and SECRET-ODD", "sentinel returned a non-JSON body SECRET-ODD"])
def test_only_a_three_digit_status_and_the_fixed_texts_pass_through(message):
    class Odd:
        base_url = "http://t"

        def check(self, *a):
            raise SentinelUnavailable(message)
    client, _ = _app(Odd())
    r = client.post("/v1/messages", json=MSG, headers=GOOD)
    assert r.status_code == 503 and "SECRET-ODD" not in r.text and "5000" not in r.text
    assert r.json()["detail"] == "sentinel check did not happen — refusing: sentinel check failed"


# ---- (2) anthropic-version ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [b"evil", b"2023-6-1", b"2023-06-01x", b"x2023-06-01", b"", b"2023/06/01",
                                   b"\xe9023-06-01", "２０２３-０６-０１".encode(), b"2023-06-01 ", b"1" * 5000],
                         ids=lambda v: repr(v)[:30])
def test_a_malformed_anthropic_version_is_a_fixed_422_and_never_forwarded(value):
    client, spy = _app(AllowSentinel())
    r = client.post("/v1/messages", json=MSG, headers={**GOOD, "anthropic-version": value})
    assert r.status_code == 422 and spy.calls == []
    assert r.json() == {"detail": "anthropic-version must be a date such as 2023-06-01"}


@pytest.mark.parametrize("value", [None, "2023-06-01", "2024-10-22", "1999-12-31"])
def test_a_date_or_no_anthropic_version_is_forwarded_as_before(value):
    client, spy = _app(AllowSentinel())
    headers = {**GOOD, **({"anthropic-version": value} if value else {})}
    r = client.post("/v1/messages", json=MSG, headers=headers)
    assert r.status_code == 200
    assert spy.calls[0]["anthropic-version"] == (value or "2023-06-01")


def test_httpx_cannot_encode_a_non_ascii_header_so_it_must_never_reach_the_upstream_call(monkeypatch):
    """Measured: this is the 500 the date check prevents (real_upstream builds the request with the caller's string)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.example.test")
    with pytest.raises(UnicodeEncodeError):
        real_upstream(MSG, {"anthropic-version": "\xe92023"})


# ---- (3) the identity headers ------------------------------------------------------------------------------------------

BAD_VALUES = ["x" * 129, "a\nb", "a\rb", "a\tb", "a\x00b", "a\x7fb", "a‮b", "a​b", " lead", "trail ", "   "]


@pytest.mark.parametrize("header", ["x-field-agent-id", "x-field-token"])
@pytest.mark.parametrize("value", [v for v in BAD_VALUES if "\n" not in v and "\r" not in v], ids=repr)
def test_a_bad_agent_id_or_token_header_is_a_fixed_422_and_never_reaches_the_sentinel(header, value):
    sentinel = AllowSentinel()
    client, spy = _app(sentinel)
    r = client.post("/v1/messages", json=MSG, headers={**GOOD, header: value.encode("utf-8")})
    assert r.status_code == 422 and spy.calls == [] and sentinel.seen == []
    assert r.json() == {"detail": f"{header} is not valid: 1 to 128 characters, one line, no control characters"}


@pytest.mark.parametrize("value", ["x" * 600, "a\tb", "a\x00b", "a‮b"], ids=lambda v: repr(v)[:20])
def test_a_bad_action_header_is_a_fixed_422_and_never_reaches_the_sentinel(value):
    sentinel = AllowSentinel()
    client, spy = _app(sentinel)
    r = client.post("/v1/messages", json=MSG, headers={**GOOD, "x-field-action": value.encode("utf-8")})
    assert r.status_code == 422 and sentinel.seen == [] and spy.calls == []
    assert r.json() == {"detail": "x-field-action is not valid: 1 to 128 characters, one line, no control characters"}


@pytest.mark.parametrize("agent,token,action,expected_action", [
    ("invoicing-agent", "tok-1", None, EGRESS_ACTION),
    ("a" * 128, "t" * 128, "draft invoices", "draft invoices"),
    ("Spin State Labs/invoicing-agent", "tok_1.2-3", "  padded action  ", "padded action"),
    ("x", "y", "z" * 128, "z" * 128),
])
def test_good_headers_still_reach_the_sentinel_unchanged(agent, token, action, expected_action):
    sentinel = AllowSentinel()
    client, spy = _app(sentinel)
    headers = {"x-field-agent-id": agent, "x-field-token": token, **({"x-field-action": action} if action else {})}
    r = client.post("/v1/messages", json=MSG, headers=headers)
    assert r.status_code == 200
    seen = sentinel.seen[0]
    assert seen == (agent, token, expected_action)


def test_a_blank_or_missing_identity_is_still_the_401_under_enforce():
    client, spy = _app(AllowSentinel())
    assert client.post("/v1/messages", json=MSG, headers={"x-field-agent-id": "a"}).status_code == 401
    assert client.post("/v1/messages", json=MSG, headers={"x-field-token": "t"}).status_code == 401
    assert client.post("/v1/messages", json=MSG).status_code == 401
    assert client.post("/v1/messages", json=MSG, headers={"x-field-agent-id": "", "x-field-token": "t"}).status_code == 401
    assert client.post("/v1/messages", json=MSG, headers={"x-field-agent-id": "a", "x-field-token": ""}).status_code == 401
    assert spy.calls == []


@pytest.mark.parametrize("header", ["x-field-agent-id", "x-field-token", "x-field-action"])
def test_an_invisible_format_character_is_refused(header):
    """A soft hyphen (U+00AD, category Cf) is the one format character a header can carry (headers are read as latin-1)."""
    sentinel = AllowSentinel()
    client, spy = _app(sentinel)
    r = client.post("/v1/messages", json=MSG, headers={**GOOD, header: b"a\xadb"})
    assert r.status_code == 422 and sentinel.seen == [] and spy.calls == []
