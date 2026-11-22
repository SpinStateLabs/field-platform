"""S7-23 (the part PR 517 leaves): a BLOCK or ESCALATE reply whose `reasons` is not a list of strings must still raise the
typed ActionBlocked / ActionEscalated. `'; '.join(verdict.get('reasons', []))` raised TypeError for a number, null or a
list holding non-strings (and, for a string, silently joined its characters), so a caller that catches ActionBlocked
saw an untyped crash. The wrapped function never ran in either case; this pins that too."""
from __future__ import annotations

import pytest

from conformance_sentinel.governed import ActionBlocked, ActionEscalated, Governor, governed


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._b = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._b


class _Client:
    def __init__(self, body):
        self.body = body

    def post(self, url, json=None, **kw):
        return _Resp(self.body)


def _gov(body):
    return Governor("agent-1", token_id="t", sentinel_url="http://sentinel.invalid", client=_Client(body))


ODD = [5, None, {"a": 1}, True, [1, 2], [None], ["ok", 3, None, "also ok"]]


@pytest.mark.parametrize("reasons", ODD, ids=["int", "null", "dict", "bool", "ints", "nulls", "mixed"])
@pytest.mark.parametrize("decision, exc", [("BLOCK", ActionBlocked), ("ESCALATE", ActionEscalated)])
def test_odd_reasons_still_raise_the_typed_exception(decision, exc, reasons):
    with pytest.raises(exc) as info:
        _gov({"decision": decision, "clause_id": "D.scope", "reasons": reasons}).check("act")
    assert str(info.value).startswith(f"{decision} [D.scope]")
    assert info.value.verdict["decision"] == decision


def test_a_missing_reasons_key_is_an_empty_message():
    with pytest.raises(ActionBlocked) as info:
        _gov({"decision": "BLOCK", "clause_id": "D.scope"}).check("act")
    assert str(info.value) == "BLOCK [D.scope] "


def test_a_string_reasons_is_one_reason_not_a_join_of_its_characters():
    with pytest.raises(ActionBlocked) as info:
        _gov({"decision": "BLOCK", "clause_id": "D.scope", "reasons": "not in scope"}).check("act")
    assert str(info.value) == "BLOCK [D.scope] not in scope"


def test_a_list_of_strings_joins_as_before_and_non_strings_are_dropped():
    with pytest.raises(ActionBlocked) as info:
        _gov({"decision": "BLOCK", "clause_id": "D.scope", "reasons": ["a", "b"]}).check("act")
    assert str(info.value) == "BLOCK [D.scope] a; b"
    with pytest.raises(ActionEscalated) as info:
        _gov({"decision": "ESCALATE", "clause_id": "E.x", "reasons": ["a", 3, "c"]}).check("act")
    assert str(info.value) == "ESCALATE [E.x] a; c"


@pytest.mark.parametrize("reasons", ODD, ids=["int", "null", "dict", "bool", "ints", "nulls", "mixed"])
def test_the_governed_function_never_runs_on_a_block_with_odd_reasons(monkeypatch, reasons):
    ran = []
    body = {"decision": "BLOCK", "clause_id": "D.scope", "reasons": reasons}
    monkeypatch.setattr("conformance_sentinel.governed.httpx.Client", lambda **kw: _Client(body))

    @governed("agent-1", "some action", sentinel_url="http://sentinel.invalid")
    def act():
        ran.append(1)

    with pytest.raises(ActionBlocked):
        act()
    assert ran == []
