"""S12-17: a BOM-prefixed secret file reads as the bare secret, in both readers.

str.strip() leaves U+FEFF, so a file written by PowerShell Out-File (or `>`) kept the BOM inside the secret, which httpx
cannot encode into a header: direction 2 lost its outcome and `verify-witness --secret-file` printed a misleading
'events source unreadable'. Both readers now use utf-8-sig."""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from sealed_ledger import witness as w
from sealed_ledger.cli import app as cli_app
from test_witness import FLY_SECRET, StubFly, _witness, env, local, served  # noqa: F401 (fixtures)

runner = CliRunner()
BOM = b"\xef\xbb\xbf"


def _write(tmp_path, raw: bytes):
    f = tmp_path / "fly-secret"
    f.write_bytes(raw)
    return f


def test_direction_2_with_a_bom_secret_file_posts_the_bare_secret(env, local, tmp_path):  # noqa: F811
    _, url = local
    env.setenv(w.FLY_SECRET_FILE_ENV, str(_write(tmp_path, BOM + FLY_SECRET.encode() + b"\n")))
    stub = StubFly()
    outcome = _witness(stub, url).tick()
    assert outcome.direction2 == "posted"
    post = [r for r in stub.requests if r.method == "POST"][0]
    assert post.headers["x-field-auth"] == FLY_SECRET


def test_direction_2_with_a_bom_only_secret_file_sends_nothing(env, local, tmp_path):  # noqa: F811
    _, url = local
    env.setenv(w.FLY_SECRET_FILE_ENV, str(_write(tmp_path, BOM + b"\n")))
    stub = StubFly()
    assert _witness(stub, url).tick().direction2 == "secret-unreadable"
    assert [r.method for r in stub.requests] == ["GET"]


@pytest.fixture()
def seen(monkeypatch):
    """Route fetch_events' httpx.Client through a MockTransport that records each request."""
    requests: list[httpx.Request] = []
    real = httpx.Client

    def factory(**kw):
        kw.pop("transport", None)
        return real(transport=httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(200, json=[])), **kw)

    monkeypatch.setattr(w.httpx, "Client", factory)
    return requests


def _verify(tmp_path, secret_file):
    return runner.invoke(cli_app, ["verify-witness", "--estate", "fly", "--events-url", "https://fly.test/events",
                                   "--secret-file", str(secret_file), "--path", str(tmp_path / "events.jsonl")])


def test_verify_witness_with_a_bom_secret_file_sends_the_bare_secret(tmp_path, seen):
    res = _verify(tmp_path, _write(tmp_path, BOM + FLY_SECRET.encode() + b"\n"))
    assert "UnicodeEncodeError" not in res.output and "unreadable" not in res.output
    assert [r.headers.get("x-field-auth") for r in seen] == [FLY_SECRET]


def test_verify_witness_with_a_bom_only_secret_file_sends_no_header(tmp_path, seen):
    res = _verify(tmp_path, _write(tmp_path, BOM + b"\n"))
    assert "UnicodeEncodeError" not in res.output and "unreadable" not in res.output
    assert [r.headers.get("x-field-auth") for r in seen] == [None]
