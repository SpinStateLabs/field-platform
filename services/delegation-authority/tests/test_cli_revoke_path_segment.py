"""S11-16: `delegation revoke <token-id>` sends the id as ONE encoded path segment.

The id was interpolated into `/tokens/{id}/revoke`: a `/`, `?`, `#` or `%` changed the route or turned the tail into a
query, and `.` / `..` is resolved by httpx into another route. As in the kill-switch CLI (`_q`): the id is quoted with
`safe=""`, and `.` / `..` are refused with exit 2 before any request. Only `revoke` interpolates an id into a path
(`introspect` and `oauth-introspect` use a body, `list` uses params).
"""
from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from delegation_authority import cli

runner = CliRunner()
BASE = "http://da.invalid"
UUID = "3f2b8c1e-9d4a-4e7b-8a61-0c5d2e9f7a13"


@pytest.fixture
def sent(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"token_id": "x", "revoked": True})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))
    monkeypatch.setenv("FIELD_DELEGATION_URL", BASE)
    monkeypatch.setenv("FIELD_OPERATOR", "op-made-up")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", "key-made-up")
    monkeypatch.delenv("FIELD_OPERATOR_KEY_FILE", raising=False)
    return seen


def _revoke(token_id):
    return runner.invoke(cli.app, ["revoke", token_id])


@pytest.mark.parametrize("token_id,path", [
    (UUID, f"/tokens/{UUID}/revoke"),
    ("a/b", "/tokens/a%2Fb/revoke"),
    ("a?b", "/tokens/a%3Fb/revoke"),
    ("a#b", "/tokens/a%23b/revoke"),
    ("a%2Fb", "/tokens/a%252Fb/revoke"),
    ("a b", "/tokens/a%20b/revoke"),
    ("é", "/tokens/%C3%A9/revoke"),
    ("a?x=1/../b#f", "/tokens/a%3Fx%3D1%2F..%2Fb%23f/revoke"),
])
def test_the_id_is_one_encoded_path_segment(sent, token_id, path):
    res = _revoke(token_id)
    assert res.exit_code == 0, res.output
    assert len(sent) == 1
    assert sent[0].method == "POST" and sent[0].url.raw_path.decode() == path
    assert sent[0].url.query == b""


@pytest.mark.parametrize("bad", [".", ".."])
def test_dot_ids_are_refused_before_any_request(sent, bad):
    res = _revoke(bad)
    assert res.exit_code == 2, res.output
    assert "may not be" in res.output and "nothing was sent" in res.output
    assert sent == []


def test_an_id_with_a_query_character_stays_on_the_guarded_revoke_route_and_carries_the_pair(sent):
    """Before the fix 'a?b' built /tokens/a?b/revoke: a query on /tokens/a, a different route. Encoded, it is the
    revoke route (the guard matches the decoded path `/tokens/a?b/revoke`) and carries the operator identity."""
    assert _revoke("a?b").exit_code == 0
    assert sent[0].headers.get("x-field-operator") == "op-made-up"
    assert sent[0].headers.get("x-field-operator-key") == "key-made-up"


def test_known_limit_an_id_with_a_slash_reaches_the_right_route_but_the_pair_does_not_ride_it(sent):
    """The guard (`is_guarded`, field-core's origin test) matches `request.url.path`, which httpx DECODES: the decoded
    path `/tokens/a/b/revoke` is not the guarded shape, so the pair is withheld (fails closed: under
    FIELD_OPERATOR_REQUIRE the service answers 401). Pinned so a change to the guard is noticed; not widened here."""
    assert _revoke("a/b").exit_code == 0
    assert sent[0].url.raw_path.decode() == "/tokens/a%2Fb/revoke"
    assert sent[0].headers.get("x-field-operator") is None


def test_the_other_verbs_are_unchanged(sent):
    assert runner.invoke(cli.app, ["introspect", "a/b"]).exit_code in (0, 1)
    assert sent[-1].url.raw_path.decode() == "/introspect"
    assert runner.invoke(cli.app, ["list"]).exit_code == 0
    assert sent[-1].url.raw_path.decode().startswith("/tokens")
