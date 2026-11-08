"""S11-23: the served-ledger helpers of the CLI never print a credential, an exception text or a traceback.

`_call_served` printed `ledger at {base_url} unreachable: {ClassName}: {exc}` (the URL, with its userinfo, and httpx's
text, which can carry it again); `_served_base_url` accepted a `FIELD_LEDGER_URL` with `user:pass@`; `_served_detail`
raised AttributeError for a JSON body that is not an object; a 2xx with a non-JSON body (`retention check`, and the
served mutating verbs through `_served_or_exit`) was a traceback. As for `--events-url` (S3-16): the origin is shown,
never userinfo, path or query; a URL carrying credentials is refused (exit 2, fixed text); a bad body is exit 2.
"""
from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from sealed_ledger.cli import app as cli_app

runner = CliRunner()
REAL_CLIENT = httpx.Client
SECRET = "hunter2"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for v in ("FIELD_LEDGER_URL", "FIELD_LEDGER_ANCHOR_KEY", "FIELD_SHARED_SECRET"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture()
def serve(monkeypatch):
    """Route the helpers' httpx.Client through a MockTransport; returns a setter for the reply (or the raise)."""
    box = {"r": lambda req: httpx.Response(200, json={"ok": True})}
    seen = []

    def factory(**kw):
        kw.pop("transport", None)
        return REAL_CLIENT(transport=httpx.MockTransport(lambda req: (seen.append(req), box["r"](req))[1]), **kw)

    monkeypatch.setattr(httpx, "Client", factory)
    monkeypatch.setenv("FIELD_LEDGER_URL", "http://ledger.test:8002/ledger")

    def setter(f):
        box["r"] = f
    setter.seen = seen
    return setter


def _clean(r):
    assert isinstance(r.exception, SystemExit) or r.exception is None, repr(r.exception)
    assert "Traceback" not in r.output


# -- the unreachable line -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("url,shown", [
    (f"http://alice:{SECRET}@ledger.test:8002/ledger?token=t0k", "http://ledger.test:8002"),
])
def test_an_unreachable_ledger_prints_the_class_and_the_origin_only(serve, monkeypatch, url, shown):
    monkeypatch.setenv("FIELD_LEDGER_URL", url.replace(f"alice:{SECRET}@", ""))   # a clean URL with a path and query
    serve(lambda req: (_ for _ in ()).throw(httpx.ConnectError(f"boom {req.url} {SECRET} t0k", request=req)))
    r = runner.invoke(cli_app, ["retention", "check"])
    assert r.exit_code == 2, r.output
    _clean(r)
    line = next(ln for ln in r.stderr.splitlines() if "unreachable" in ln)
    assert line == f"error: ledger at {shown} unreachable: ConnectError"
    for leak in (SECRET, "t0k", ":8002/ledger", "boom"):
        assert leak not in r.output


def test_the_exception_text_is_never_printed(serve):
    serve(lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("SECRET-TEXT-IN-EXC", request=req)))
    r = runner.invoke(cli_app, ["retention", "check"])
    assert r.exit_code == 2 and "ReadTimeout" in r.stderr and "SECRET-TEXT-IN-EXC" not in r.output


# -- a FIELD_LEDGER_URL carrying credentials ---------------------------------------------------------------------


@pytest.mark.parametrize("url", [f"http://alice:{SECRET}@ledger.test:8002", f"https://{SECRET}@ledger.test/x",
                                 f"http://:{SECRET}@ledger.test", "http://alice@ledger.test"])
def test_a_ledger_url_with_userinfo_is_refused_before_any_request(serve, monkeypatch, url):
    monkeypatch.setenv("FIELD_LEDGER_URL", url)
    r = runner.invoke(cli_app, ["retention", "check"])
    assert r.exit_code == 2, r.output
    _clean(r)
    assert "FIELD_LEDGER_URL must not carry credentials" in r.stderr
    assert SECRET not in r.output and "alice" not in r.output and "ledger.test" not in r.output
    assert serve.seen == []


def test_the_userinfo_refusal_covers_the_mutating_verbs_too(serve, monkeypatch):
    monkeypatch.setenv("FIELD_LEDGER_URL", f"http://alice:{SECRET}@ledger.test")
    for args in (["hold", "place", "--by", "o", "--reason", "r"], ["hold", "release", "--by", "o"]):
        r = runner.invoke(cli_app, args)
        assert r.exit_code == 2 and SECRET not in r.output
    assert serve.seen == []


def test_a_clean_url_still_works_and_offline_ignores_the_variable(serve, monkeypatch):
    serve(lambda req: httpx.Response(200, json={"ok": True}))
    r = runner.invoke(cli_app, ["retention", "check"])
    assert r.exit_code == 0, r.output
    assert serve.seen[0].url.path == "/ledger/retention/check"


# -- _served_detail and the 2xx body --------------------------------------------------------------------------------


@pytest.mark.parametrize("body", ['["a", "b"]', '"just a string"', "42", "null", "<html>"])
def test_a_non_object_error_body_is_a_refusal_not_an_attribute_error(serve, body):
    serve(lambda req: httpx.Response(500, content=body.encode()))
    r = runner.invoke(cli_app, ["hold", "place", "--by", "o", "--reason", "r"])
    assert r.exit_code == 1, r.output                         # a 500 is "ledger corrupt" (exit 1) as before
    _clean(r)


@pytest.mark.parametrize("body", ['["a"]', '"x"', "null", "7"])
def test_a_2xx_retention_check_body_that_is_not_an_object_is_exit_2(serve, body):
    serve(lambda req: httpx.Response(200, content=body.encode()))
    r = runner.invoke(cli_app, ["retention", "check"])
    assert r.exit_code == 2, r.output
    _clean(r)
    assert body not in r.output


def test_a_2xx_retention_check_that_is_not_json_is_exit_2_with_fixed_text(serve):
    serve(lambda req: httpx.Response(200, text="<html>SECRET-BODY</html>"))
    r = runner.invoke(cli_app, ["retention", "check"])
    assert r.exit_code == 2, r.output
    _clean(r)
    assert "SECRET-BODY" not in r.output and "not JSON" in r.stderr


def test_a_2xx_mutating_verb_with_a_non_json_body_is_exit_2(serve):
    serve(lambda req: httpx.Response(200, text="<html>SECRET-BODY</html>"))
    r = runner.invoke(cli_app, ["hold", "place", "--by", "o", "--reason", "r"])
    assert r.exit_code == 2, r.output
    _clean(r)
    assert "SECRET-BODY" not in r.output


def test_a_good_retention_check_keeps_its_exit_codes(serve):
    serve(lambda req: httpx.Response(200, json={"ok": True}))
    assert runner.invoke(cli_app, ["retention", "check"]).exit_code == 0
    serve(lambda req: httpx.Response(200, json={"ok": False}))
    assert runner.invoke(cli_app, ["retention", "check"]).exit_code == 3


@pytest.mark.parametrize("url,shown", [
    (f"http://alice:{SECRET}@ledger.test:8002/ledger?token=t0k#frag", "http://ledger.test:8002"),
    (f"https://{SECRET}@Ledger.Test/x", "https://ledger.test"),
    ("http://ledger.test", "http://ledger.test"),
    ("http://[::1]:9", "http://[::1]:9"),
])
def test_origin_is_scheme_host_port_only(url, shown):
    from sealed_ledger.cli import _origin
    assert _origin(url) == shown


def test_origin_of_an_unparseable_url_is_a_fixed_placeholder():
    from sealed_ledger.cli import _origin
    assert _origin("http://[::1") == "<unparseable URL>"
    assert _origin("http://h:99999999999") == "<unparseable URL>"
