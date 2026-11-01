"""C-503: bootstrap.register and bootstrap.mint never put the registry's or the delegation service's body in an error."""
from __future__ import annotations

import pytest

from field_agent import bootstrap
from field_agent.errors import BootstrapError

MARK = "CANARY-8f31-zq"          # made up; stands in for a value an upstream echoes back
BIG = MARK + "x" * 5000


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


def test_mint_names_the_status_and_not_the_body():
    with pytest.raises(BootstrapError) as exc:
        bootstrap.mint("a", "me", ["draft"], ttl_seconds=60, client=Upstream(500), delegation_url="http://delegation.invalid")
    assert str(exc.value) == "mint returned 500"
