"""S4-3: delegation CLI verbs (mint, revoke, introspect, oauth-introspect, list) had no tests, and:
 * `_fail` called resp.json().get(...) so a non-JSON error body (a proxy's 502 page) or a non-object JSON body was a
   traceback;
 * no verb caught a transport error: a down service printed a traceback, and the exception text can hold the URL;
 * revoke built the URL from raw text (an id with / ? # changed the route);
 * introspect and oauth-introspect called resp.json().get('active') unguarded (a 200 with a bad body crashed).
httpx.MockTransport stands in for the service; nothing leaves the process. The doa verb and the operator-pair code
are tested elsewhere and not touched."""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from delegation_authority import cli

runner = CliRunner()
TOKEN = {"token_id": "t1", "agent_id": "a1", "granted_by": "Don", "scope": ["read"],
         "issued_at": "2026-11-04T00:00:00+00:00", "expires_at": "2026-11-04T01:00:00+00:00", "revoked": False}


@pytest.fixture()
def svc(monkeypatch):
    """(requests, set_handler): every CLI client talks to a MockTransport."""
    seen: list[httpx.Request] = []
    box = {"h": lambda r: httpx.Response(200, json={})}

    def handler(request):
        seen.append(request)
        return box["h"](request)

    monkeypatch.setattr(cli, "_client", lambda pair=None, timeout=10.0: httpx.Client(
        transport=httpx.MockTransport(handler), timeout=timeout))
    return seen, lambda f: box.__setitem__("h", f)


MINT = ["mint", "a1", "--granted-by", "Don", "--scope", "read", "--scope", "write", "--ttl", "60"]


def test_mint_prints_the_token_and_sends_the_scopes_and_ttl(svc):
    seen, set_h = svc
    set_h(lambda r: httpx.Response(201, json=TOKEN))
    res = runner.invoke(cli.app, MINT)
    assert res.exit_code == 0 and json.loads(res.stdout)["token_id"] == "t1"
    body = json.loads(seen[0].content)
    assert body == {"agent_id": "a1", "granted_by": "Don", "scope": ["read", "write"], "ttl_seconds": 60}
    assert seen[0].url.path == "/tokens"


def test_mint_a_non_201_is_error_status_detail_exit_1(svc):
    _, set_h = svc
    set_h(lambda r: httpx.Response(403, json={"detail": "grantor not on roster"}))
    res = runner.invoke(cli.app, MINT)
    assert res.exit_code == 1 and "error 403: grantor not on roster" in res.stderr and res.stdout == ""


def test_revoke_prints_the_answer_and_a_404_is_exit_1(svc):
    seen, set_h = svc
    set_h(lambda r: httpx.Response(200, json={"revoked": True}))
    assert runner.invoke(cli.app, ["revoke", "t1"]).exit_code == 0
    set_h(lambda r: httpx.Response(404, json={"detail": "unknown token"}))
    res = runner.invoke(cli.app, ["revoke", "t1"])
    assert res.exit_code == 1 and "error 404: unknown token" in res.stderr


@pytest.mark.parametrize("verb", [["introspect", "t1"], ["oauth-introspect", "t1"]])
@pytest.mark.parametrize("active,code", [(True, 0), (False, 1)])
def test_introspect_verbs_exit_0_only_when_active(svc, verb, active, code):
    _, set_h = svc
    set_h(lambda r: httpx.Response(200, json={"active": active}))
    res = runner.invoke(cli.app, verb)
    assert res.exit_code == code and json.loads(res.stdout)["active"] is active


def test_introspect_sends_the_token_where_the_service_reads_it(svc):
    seen, _ = svc
    runner.invoke(cli.app, ["introspect", "t1"])
    runner.invoke(cli.app, ["oauth-introspect", "t2"])
    assert seen[0].url.path == "/introspect" and json.loads(seen[0].content) == {"token_id": "t1"}
    assert seen[1].url.path == "/oauth/introspect" and seen[1].content == b"token=t2"


def test_list_passes_the_agent_filter_and_prints_the_answer(svc):
    seen, set_h = svc
    set_h(lambda r: httpx.Response(200, json=[TOKEN]))
    res = runner.invoke(cli.app, ["list", "--agent-id", "a1"])
    assert res.exit_code == 0 and json.loads(res.stdout)[0]["token_id"] == "t1"
    assert seen[0].url.params["agent_id"] == "a1"
    runner.invoke(cli.app, ["list"])
    assert "agent_id" not in seen[1].url.params


# ---- (1) _fail on a body that is not an object with a detail ------------------------------------------------------


@pytest.mark.parametrize("body", [b"<html>502 Bad Gateway</html>", b"[1, 2]", b'"oops"', b""])
@pytest.mark.parametrize("argv", [MINT, ["revoke", "t1"], ["introspect", "t1"], ["oauth-introspect", "t1"], ["list"]])
def test_an_error_with_a_non_object_body_is_one_status_line_exit_1(svc, argv, body):
    _, set_h = svc
    set_h(lambda r: httpx.Response(502, content=body))
    res = runner.invoke(cli.app, argv)
    assert res.exit_code == 1 and isinstance(res.exception, SystemExit)
    assert res.stderr.strip() == "error 502: no usable error detail in the reply"
    assert "<html>" not in res.output and "Traceback" not in res.output


def test_a_json_error_without_a_detail_still_prints_what_it_said(svc):
    _, set_h = svc
    set_h(lambda r: httpx.Response(500, json={"message": "boom"}))
    res = runner.invoke(cli.app, ["list"])
    assert res.exit_code == 1 and "error 500:" in res.stderr and "boom" in res.stderr


# ---- (2) an unreachable service ---------------------------------------------------------------------------------


@pytest.mark.parametrize("argv,nothing", [(MINT, "nothing was minted"), (["revoke", "t1"], "nothing was revoked"),
                                          (["introspect", "t1"], None), (["oauth-introspect", "t1"], None),
                                          (["list"], None)])
@pytest.mark.parametrize("exc", [httpx.ConnectError("secret-host.invalid refused"), httpx.ReadTimeout("slow")])
def test_an_unreachable_service_is_one_line_exit_2_with_no_exception_text(svc, argv, nothing, exc):
    _, set_h = svc

    def boom(request):
        raise exc

    set_h(boom)
    res = runner.invoke(cli.app, argv)
    assert res.exit_code == 2 and isinstance(res.exception, SystemExit)
    assert f"error: delegation-authority unreachable ({type(exc).__name__})" in res.stderr
    assert "secret-host" not in res.output and "invalid" not in res.output and "Traceback" not in res.output
    if nothing:
        assert nothing in res.stderr


# ---- (3) the revoke id is one path segment ------------------------------------------------------------------------


def test_a_revoke_id_with_url_metacharacters_is_one_encoded_path_segment(svc):
    seen, _ = svc
    runner.invoke(cli.app, ["revoke", "a/../b?x=1#f"])
    assert seen[0].url.raw_path.decode() == "/tokens/a%2F..%2Fb%3Fx%3D1%23f/revoke"


# ---- (4) a 200 whose body has no usable `active` -------------------------------------------------------------------


@pytest.mark.parametrize("verb", [["introspect", "t1"], ["oauth-introspect", "t1"]])
@pytest.mark.parametrize("body", [b"not json", b"[1]", b'"x"', b""])
def test_a_200_without_a_json_object_fails_closed_exit_1(svc, verb, body):
    _, set_h = svc
    set_h(lambda r: httpx.Response(200, content=body))
    res = runner.invoke(cli.app, verb)
    assert res.exit_code == 1 and isinstance(res.exception, SystemExit)
    assert "not a JSON object" in res.stderr and "Traceback" not in res.output


@pytest.mark.parametrize("verb", [["introspect", "t1"], ["oauth-introspect", "t1"]])
def test_an_object_with_no_active_key_is_not_active(svc, verb):
    _, set_h = svc
    set_h(lambda r: httpx.Response(200, json={"other": 1}))
    assert runner.invoke(cli.app, verb).exit_code == 1
