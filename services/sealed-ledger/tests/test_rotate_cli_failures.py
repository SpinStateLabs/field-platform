"""S7-19 — `ledger rotate` fails cleanly: a failed --anchors write after a completed rotation keeps
the result (exit 1, anchor printed off-box), a non-JSON 2xx and a malformed FIELD_LEDGER_URL are one
stderr line (exit 2), never a traceback, and a URL's userinfo is never printed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ledger_c2_support import KEY_PRIV, fill
from sealed_ledger import cli
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore

runner = CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for v in ("FIELD_LEDGER_URL", "FIELD_LEDGER_ANCHOR_KEY", "FIELD_SHARED_SECRET"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture()
def seg(tmp_path):
    p = tmp_path / "ledger" / "events.jsonl"
    fill(LedgerStore(p), 3)
    key = tmp_path / "anchor.pem"
    key.write_text(KEY_PRIV, encoding="ascii")
    return p, key


def _offline(p, key, *extra):
    return runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r", "--offline",
                                   "--path", str(p), "--key", str(key), *extra])


def _no_traceback(r):
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
    assert "Traceback" not in r.output


def test_anchors_path_is_a_directory(seg, tmp_path):
    p, key = seg
    d = tmp_path / "adir"
    d.mkdir()
    r = _offline(p, key, "--anchors", str(d))
    assert r.exit_code == 1, r.output
    _no_traceback(r)
    assert json.loads(r.stdout)["segment"] == 1          # the result was printed FIRST
    assert "rotation SUCCEEDED" in r.stderr and "NOT written" in r.stderr
    assert "Do NOT re-run rotate" in r.stderr
    assert '"head_hash"' in r.stderr                      # the anchor, to store off-box
    assert (p.parent / json.loads(r.stdout)["file"]).exists()  # really rotated


def test_anchors_path_under_a_file(seg, tmp_path):
    p, key = seg
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    r = _offline(p, key, "--anchors", str(blocker / "sub" / "a.jsonl"))
    assert r.exit_code == 1, r.output
    _no_traceback(r)
    assert json.loads(r.stdout)["segment"] == 1
    assert "NOT written" in r.stderr


def test_a_writable_anchors_path_is_unchanged(seg, tmp_path):
    p, key = seg
    a = tmp_path / "a.jsonl"
    r = _offline(p, key, "--anchors", str(a))
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["segment"] == 1 and a.read_text().count("\n") == 1


class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text

    def json(self):
        return json.loads(self.text)


@pytest.mark.parametrize("args, text", [
    (["rotate", "--operator", "o", "--reason", "r"], "<html>not json</html>"),
    (["rotate", "--operator", "o", "--reason", "r"], '{"unexpected": 1}'),
    (["hold", "place", "--by", "o", "--reason", "r"], "<html>not json</html>"),
])
def test_a_2xx_that_is_not_the_expected_body_is_exit_2(monkeypatch, args, text):
    monkeypatch.setenv("FIELD_LEDGER_URL", "http://ledger.test")
    monkeypatch.setattr(cli, "_call_served", lambda *a, **k: _Resp(200, text))
    r = runner.invoke(cli_app, args)
    assert r.exit_code == 2, r.output
    _no_traceback(r)
    assert text not in r.output                       # the body is not echoed


@pytest.mark.parametrize("url", ["http://[::1", "http://user:hunter2@[::1", "http://exa mple.test:99999999"])
def test_a_malformed_ledger_url_is_exit_2_and_not_echoed(monkeypatch, url):
    monkeypatch.setenv("FIELD_LEDGER_URL", url)
    r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r"])
    assert r.exit_code == 2, r.output
    _no_traceback(r)
    assert "hunter2" not in r.output and url not in r.output


def test_unreachable_url_does_not_print_userinfo(monkeypatch):
    monkeypatch.setenv("FIELD_LEDGER_URL", "http://alice:hunter2@127.0.0.1:1")
    r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r"])
    assert r.exit_code == 2, r.output
    assert "unreachable" in r.stderr and "hunter2" not in r.output and "alice" not in r.output


def test_a_nul_byte_in_the_anchors_path_is_the_same_clean_exit_1(seg, tmp_path):
    p, key = seg
    r = _offline(p, key, "--anchors", str(tmp_path / "a\x00b.jsonl"))
    assert r.exit_code == 1, r.output
    _no_traceback(r)
    assert json.loads(r.stdout)["segment"] == 1 and "NOT written" in r.stderr
