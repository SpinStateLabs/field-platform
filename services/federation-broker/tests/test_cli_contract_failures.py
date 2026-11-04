"""S5-12: ``fedbroker add-contract`` and ``contracts`` with the service down or answering garbage: one stderr line and
exit 1, never a traceback; the contract id is one URL path segment whatever it holds."""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from federation_broker import cli as cli_mod

runner = CliRunner()
ARGS = ["add-contract", "FED-1", "--org", "Acme", "--scope", "s", "--data-class", "d"]


class Stub:
    """Stands in for the ``httpx`` module inside the CLI and records the URLs it is asked for."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.urls: list[str] = []

    def _call(self, url, **kw):
        self.urls.append(url)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    put = get = _call


def resp(status, text="", **kw):
    return httpx.Response(status, text=text, **kw)


@pytest.fixture()
def run(monkeypatch):
    monkeypatch.setenv("FIELD_FEDERATION_URL", "http://127.0.0.1:8010")

    def go(outcome, *args):
        stub = Stub(outcome)
        monkeypatch.setattr(cli_mod, "httpx", stub)
        r = runner.invoke(cli_mod.app, list(args))
        assert "Traceback" not in r.output
        assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
        return r, stub
    return go


ERRORS = [httpx.ConnectError("refused"), httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"),
          httpx.UnsupportedProtocol("scheme"), httpx.RemoteProtocolError("bad"), httpx.InvalidURL("bad url")]


@pytest.mark.parametrize("exc", ERRORS, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("args", [ARGS, ["contracts"]], ids=["add-contract", "contracts"])
def test_an_unreachable_service_is_one_line_exit_1(run, exc, args):
    r, _ = run(exc, *args)
    assert r.exit_code == 1
    assert f"unreachable ({type(exc).__name__})" in r.output and "http://127.0.0.1:8010" in r.output
    assert len(r.output.strip().splitlines()) == 1


def test_the_origin_has_no_userinfo_path_or_query(run, monkeypatch):
    monkeypatch.setenv("FIELD_FEDERATION_URL", "https://user:SECRETPW@broker.example:8443/base/path?token=SECRETQ")
    r, _ = run(httpx.ConnectError("x"), "contracts")
    assert r.exit_code == 1 and "https://broker.example:8443" in r.output
    for leak in ("SECRETPW", "SECRETQ", "user", "/base"):
        assert leak not in r.output


@pytest.mark.parametrize("url", ["not a url", "", "://x", "http://"])
def test_an_unusable_env_url_does_not_traceback(run, monkeypatch, url):
    monkeypatch.setenv("FIELD_FEDERATION_URL", url)
    r, _ = run(httpx.UnsupportedProtocol("x"), "contracts")
    assert r.exit_code == 1 and "unreachable" in r.output


@pytest.mark.parametrize("args", [ARGS, ["contracts"]], ids=["add-contract", "contracts"])
def test_a_500_with_an_html_body_is_one_capped_line(run, args):
    html = "<html>" + "\n  <p>gateway exploded</p>" * 400 + "</html>"
    r, _ = run(resp(500, html), *args)
    assert r.exit_code == 1
    out = r.output.strip()
    assert out.startswith("error 500:") and len(out.splitlines()) == 1 and len(out) < 260


def test_a_json_error_still_shows_its_detail(run):
    r, _ = run(resp(409, '{"detail": "already has an active contract"}'), *ARGS)
    assert r.exit_code == 1 and "error 409: already has an active contract" in r.output


def test_an_empty_error_body_is_named(run):
    r, _ = run(resp(502, ""), "contracts")
    assert r.exit_code == 1 and "(empty body)" in r.output


def test_success_is_unchanged(run):
    r, stub = run(resp(200, '[{"contract_id": "FED-1"}]'), "contracts")
    assert r.exit_code == 0 and "FED-1" in r.output and stub.urls == ["http://127.0.0.1:8010/contracts"]


@pytest.mark.parametrize("cid,segment", [
    ("a/b", "a%2Fb"), ("a?x=1", "a%3Fx%3D1"), ("a b", "a%20b"), ("a#f", "a%23f"), ("FED-2026-001", "FED-2026-001"),
    ("a%2Fb", "a%252Fb"), ("é", "%C3%A9"),
])
def test_the_contract_id_is_one_path_segment(run, cid, segment):
    r, stub = run(resp(200, "{}"), "add-contract", cid, "--org", "Acme", "--scope", "s", "--data-class", "d")
    assert r.exit_code == 0, r.output
    assert stub.urls == [f"http://127.0.0.1:8010/contracts/{segment}"]


# ---- end to end against the real app ------------------------------------------------------------------------------

class Routed:
    def __init__(self, client):
        self.client = client

    def _call(self, verb):
        def call(url, **kw):
            kw.pop("timeout", None)
            return getattr(self.client, verb)(url, **kw)
        return call

    def __getattr__(self, verb):
        if verb in ("get", "put"):
            return self._call(verb)
        raise AttributeError(verb)


@pytest.fixture()
def real(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from federation_broker.api import create_app
    from federation_broker.engine import BrokerEngine, ContractStore

    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    client = TestClient(create_app(engine=BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"))))
    monkeypatch.setattr(cli_mod, "httpx", Routed(client))
    monkeypatch.setenv("FIELD_FEDERATION_URL", "http://testserver")
    return client


@pytest.mark.parametrize("cid", ["a?x=1", "a#frag", "a b"])
def test_an_id_with_a_url_special_character_registers_and_lists_as_itself(real, cid):
    r = runner.invoke(cli_mod.app, ["add-contract", cid, "--org", "Acme", "--scope", "s", "--data-class", "d"])
    assert r.exit_code == 0, r.output
    assert [c["contract_id"] for c in real.get("/contracts").json()] == [cid]


@pytest.mark.parametrize("cid", ["a/b", "a%2Fb"])
def test_a_slash_or_an_escape_in_the_id_is_still_a_clean_404_not_a_traceback(real, cid):
    """The service's route takes one path segment and the server decodes %2F before routing: an id with '/' (or a
    literal %2F) cannot be registered through this API (a pre-existing limit, pinned so a change is noticed). The CLI
    answers in one line."""
    r = runner.invoke(cli_mod.app, ["add-contract", cid, "--org", "Acme", "--scope", "s", "--data-class", "d"])
    assert r.exit_code == 1 and r.output.startswith("error 404") and "Traceback" not in r.output
