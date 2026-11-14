"""S11-2: bootstrap.register / bootstrap.mint turn a 201 with an unusable body into a BootstrapError, and an
unreachable service into a type-name-only message.

Before: `resp.json()` was returned unguarded (register) or fed to `model_validate` (mint), so a 201 whose body is not
JSON, not an object or not a token escaped as ValueError / ValidationError (a traceback from `fieldagent mint`) AFTER
the server had created the record, and a retry would create a second one. And the unreachable message carried
`{exc}`, whose text holds the URL, a proxy or an address.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from field_agent import bootstrap, cli
from field_agent.errors import BootstrapError

MARK = "CANARY-3c7e-pq"


class Resp:
    def __init__(self, status: int, text: str):
        self.status_code, self.text = status, text

    def json(self):
        return json.loads(self.text)


class Client:
    def __init__(self, reply=None, exc: Exception | None = None):
        self.reply, self.exc = reply, exc

    def post(self, url, **kw):
        if self.exc is not None:
            raise self.exc
        return self.reply


def _token(**over):
    now = datetime.now(timezone.utc)
    rec = {"token_id": "t1", "agent_id": "a", "granted_by": "me", "scope": ["draft"],
           "issued_at": now.isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat()}
    rec.update(over)
    return rec


def _register(client):
    return bootstrap.register("a", "n", "o", client=client, registry_url="http://registry.invalid")


def _mint(client):
    return bootstrap.mint("a", "me", ["draft"], ttl_seconds=60, client=client, delegation_url="http://delegation.invalid")


BAD_BODIES = [MARK + " not json", "[]", f'["{MARK}"]', "{}", "null", '"' + MARK + '"', "42"]


@pytest.mark.parametrize("body", BAD_BODIES + [json.dumps({"agent_id": 5}), json.dumps({"name": MARK})])
def test_register_201_with_an_unusable_body_is_a_bootstrap_error(body):
    with pytest.raises(BootstrapError) as exc:
        _register(Client(Resp(201, body)))
    text = str(exc.value)
    assert text == "register answered 201 with an unusable body; the agent may be registered, check before retrying"
    assert MARK not in text


@pytest.mark.parametrize("body", BAD_BODIES + [json.dumps({"agent_id": 5}), json.dumps({"name": MARK})])
def test_mint_201_with_an_unusable_body_is_a_bootstrap_error(body):
    with pytest.raises(BootstrapError) as exc:
        _mint(Client(Resp(201, body)))
    text = str(exc.value)
    assert text == "mint answered 201 with an unusable body; the token may be minted, check before retrying"
    assert MARK not in text


def test_mint_201_missing_a_required_field_is_a_bootstrap_error():
    rec = _token()
    del rec["expires_at"]
    with pytest.raises(BootstrapError):
        _mint(Client(Resp(201, json.dumps(rec))))


def test_mint_201_with_an_extra_field_is_a_bootstrap_error_that_does_not_name_it():
    with pytest.raises(BootstrapError) as exc:
        _mint(Client(Resp(201, json.dumps(_token(**{MARK: 1})))))
    assert MARK not in str(exc.value)


@pytest.mark.parametrize("call", [_register, _mint])
def test_the_error_drops_the_chain(call):
    with pytest.raises(BootstrapError) as exc:
        call(Client(Resp(201, MARK + " not json")))
    assert exc.value.__cause__ is None and exc.value.__suppress_context__ is True


def test_good_201_bodies_are_unchanged():
    assert _register(Client(Resp(201, json.dumps({"agent_id": "a", "status": "active"}))))["agent_id"] == "a"
    assert _mint(Client(Resp(201, json.dumps(_token())))).token_id == "t1"


@pytest.mark.parametrize("call,service", [(_register, "agent-registry"), (_mint, "delegation-authority")])
def test_unreachable_names_the_exception_type_and_not_its_text(call, service):
    url = "http://10.1.2.3:99/secret-path"
    with pytest.raises(BootstrapError) as exc:
        call(Client(exc=RuntimeError(url)))
    text = str(exc.value)
    assert text == f"{service} unreachable (RuntimeError)"
    assert "10.1.2.3" not in text and "secret-path" not in text
    assert exc.value.__cause__ is None and exc.value.__suppress_context__ is True


def test_non_201_statuses_are_unchanged():
    with pytest.raises(BootstrapError) as e1:
        _register(Client(Resp(409, MARK)))
    assert str(e1.value) == "register returned 409"
    with pytest.raises(BootstrapError) as e2:
        _mint(Client(Resp(500, MARK)))
    assert str(e2.value) == "mint returned 500"


def test_the_cli_mint_prints_one_error_line_and_exits_1_on_a_bad_201(monkeypatch):
    real = bootstrap.mint

    def bad(*a, **k):   # the real mint, against a client whose 201 body is unusable
        return real(*a, client=Client(Resp(201, MARK + " not json")), delegation_url="http://delegation.invalid", **k)
    monkeypatch.setattr(cli.bootstrap, "mint", bad)
    r = CliRunner().invoke(cli.app, ["mint", "a", "--granted-by", "me", "--scope", "draft"])
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)
    lines = [ln for ln in r.output.splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("error: ") and MARK not in r.output
    assert "Traceback" not in r.output
