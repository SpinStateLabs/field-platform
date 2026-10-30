"""C-503: bootstrap.register and bootstrap.mint never put the registry's or the delegation service's body in an error."""
from __future__ import annotations

import pytest

from field_agent import bootstrap
from field_agent.errors import BootstrapError

MARK = "CANARY-8f31-zq"          # made up; stands in for a value an upstream echoes back
BIG = MARK + "x" * 5000


def assert_no_body(exc):
    """The marker and the long body are on none of: str, repr, args, attributes, the cause or the context chain."""
    seen, todo = [], [exc]
    while todo:
        e = todo.pop()
        if e is None or any(e is x for x in seen):
            continue
        seen.append(e)
        todo += [e.__cause__, e.__context__]
    for e in seen:
        for text in (str(e), repr(e), repr(e.args), repr(getattr(e, "__dict__", {}))):
            assert MARK not in text and "x" * 200 not in text, (type(e).__name__, text[:120])


class Resp:
    def __init__(self, status: int, text: str):
        self.status_code, self.text = status, text


class Upstream:
    def __init__(self, status: int = 422):
        self.reply = Resp(status, BIG)

    def post(self, url, **kw):
        return self.reply


def test_register_names_the_status_and_not_the_body():
    with pytest.raises(BootstrapError) as exc:
        bootstrap.register("a", "n", "o", client=Upstream(409), registry_url="http://registry.invalid")
    assert str(exc.value) == "register returned 409"
    assert_no_body(exc.value)


def test_mint_names_the_status_and_not_the_body():
    with pytest.raises(BootstrapError) as exc:
        bootstrap.mint("a", "me", ["draft"], ttl_seconds=60, client=Upstream(500), delegation_url="http://delegation.invalid")
    assert str(exc.value) == "mint returned 500"
    assert_no_body(exc.value)
