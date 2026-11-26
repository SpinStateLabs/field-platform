"""No tool result shows a token id: it is a bearer credential. Each tool's service answers with a made-up id in every
place one can travel (known keys at depth, other keys, dict keys, free text, a text reply); the result never holds it.

Mutants: T1 the UUID-shaped replacement removed; T2 the token-key rule removed; T3 the cut made before the replacement.
"""
import hashlib
import json

import pytest

from conftest import KEY, config_for
from field_mcp import client as cl
from field_mcp import tools as tl
from field_mcp.tools import Dispatcher, build_specs

TID = "7d3f9a1c-52be-4c08-9e6a-1b2c3d4e5f60"          # made up, the shape field_core.delegation mints
OPAQUE = "made-up-opaque-credential-0001"              # not UUID-shaped: only the key rule can catch it
ARGS = {"agent_id": "a", "name": "n", "token_id": "t", "body": {}}
TOOL_NAMES = [s.name for s in build_specs(1)]


def ref(value: str) -> str:
    return "[id:" + hashlib.sha256(value.encode()).hexdigest()[:12] + "]"


def json_reply() -> dict:
    return {
        "token_id": TID, "token": OPAQUE, "x-field-token": OPAQUE, "delegation_token": OPAQUE, "X_Field_Token": OPAQUE,
        "token_ids": [TID, OPAQUE], "jti": OPAQUE,
        "deep": [{"a": {"b": [{"token_id": OPAQUE, "record_id": TID, "detail": f"token '{TID}' expired"}]}}],
        "by_token": {TID: 3, f"grant:{TID.upper()}": 1},
        "escalations": [{"escalation_id": "e-1", "reason": f"over cap, token={TID}", "token_id": TID}],
        "recent": [{"x_field_token": OPAQUE, "note": f"x-field-token: {TID}"}],
        "long": "A" * (cl.MAX_STRING - 10) + TID,
        "tokens": 7, "input_tokens": 11,
    }


def call(stub, monkeypatch, name: str, body, ctype: str):
    cfg = config_for(stub)
    d = Dispatcher(cfg, {s: cl.Upstream(s, stub.base, KEY) for s in cfg.services})
    tool = d.specs[name].tool
    stub.routes[(tool.method, cl.build_path(tool.path, ARGS))] = (200, body, {"content-type": ctype})
    monkeypatch.setattr(tl.jsonschema, "validate", lambda *a, **k: None)     # one argument set for every tool
    result = d.call(name, ARGS)
    assert result["status"] == "ok", (name, result)
    assert len(stub.requests) == 1
    return result


def assert_clean(result) -> str:
    text = json.dumps(result)
    for secret in (TID, TID.upper(), OPAQUE, TID[:18]):
        assert secret not in text
    return text


def test_the_two_reads_named_in_the_review_are_tools():
    assert {"spend_governor_list_escalations", "claude_approver_stats"} <= set(TOOL_NAMES)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_no_tool_result_shows_a_token_id_in_a_json_reply(stub, monkeypatch, name):
    result = call(stub, monkeypatch, name, json_reply(), "application/json")
    assert_clean(result)
    data = result["data"]
    assert data["token_id"] == ref(TID) and data["token"] == ref(OPAQUE) and data["token_ids"] == [ref(TID), ref(OPAQUE)]
    assert data["deep"][0]["a"]["b"][0]["detail"] == f"token '{ref(TID)}' expired"    # equal ids stay equal
    assert (data["tokens"], data["input_tokens"]) == (7, 11)                           # counts are not ids


@pytest.mark.parametrize("ctype", ["text/markdown", "text/html", "text/plain"])
@pytest.mark.parametrize("name", TOOL_NAMES)
def test_no_tool_result_shows_a_token_id_in_a_text_reply(stub, monkeypatch, name, ctype):
    body = f"| `{TID}` | revoked |\n<td>{TID}</td>\n- token {TID.upper()} (see {TID}).\n"
    result = call(stub, monkeypatch, name, body, ctype)
    assert_clean(result)
    assert ref(TID) in result["data"]["text"] and "revoked" in result["data"]["text"]


def test_an_id_across_the_length_cut_leaves_no_part(stub):
    for lead in range(cl.MAX_STRING - len(TID) - 1, cl.MAX_STRING + 1):
        out = cl._bound("A" * lead + TID, ())
        assert TID[:9] not in out


def test_the_reference_is_stable_and_not_replaced_again():
    once = cl._bound({"token_id": TID}, ())
    assert once == {"token_id": ref(TID)} and cl._bound(once, ()) == once


def test_a_configured_secret_under_a_token_key_stays_the_fixed_word():
    assert cl._bound({"token": KEY}, (KEY,)) == {"token": "[redacted]"}
