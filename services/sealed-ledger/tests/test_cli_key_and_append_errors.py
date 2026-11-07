"""S9-19: the sealed-ledger CLI turns an unusable key file or a busy or corrupt store into a one-line exit code, never a
traceback, and never echoes a decode error (its text names a byte and position of the key file).

verify --pubkey (segment and anchors branches): exit 2 naming the flag and the exception CLASS. export --sign-key and
verify-export --pubkey keep their 'cannot read' prefixes and show the class only. append: LedgerBusy is exit 4 (BUSY or
UNREADABLE), LedgerCorrupt is exit 1. Every value is made up."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from ledger_c2_support import KEY_PUB, three_segments
from sealed_ledger import store as store_module
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import UNREADABLE_PREFIX, LedgerBusy, LedgerCorrupt

runner = CliRunner()
MARK = "MARKER-2b9d"


@pytest.fixture()
def ledger(tmp_path):
    path = tmp_path / "events.jsonl"
    assert runner.invoke(cli_app, ["append", "action", "--path", str(path)]).exit_code == 0
    return path


@pytest.fixture()
def keys(tmp_path):
    missing = tmp_path / "absent.pem"
    bom = tmp_path / "bom.pem"
    bom.write_bytes(b"\xef\xbb\xbf-----BEGIN PUBLIC KEY-----\n\xe9" + MARK.encode() + b"\n")
    junk = tmp_path / "junk.pem"
    junk.write_text("not a key " + MARK, encoding="ascii")
    return {"missing": missing, "bom": bom, "junk": junk}


def no_traceback(res):
    assert "Traceback" not in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit), repr(res.exception)
    assert MARK not in res.output


KEY_CASES = [("missing", "FileNotFoundError"), ("bom", "UnicodeDecodeError"), ("junk", "ValueError")]


@pytest.mark.parametrize("name,cls", KEY_CASES)
def test_verify_anchors_with_an_unusable_pubkey_is_exit_2(ledger, tmp_path, keys, name, cls):
    res = runner.invoke(cli_app, ["verify", "--path", str(ledger), "--anchors", str(tmp_path / "a.jsonl"),
                                  "--pubkey", str(keys[name])])
    assert res.exit_code == 2, res.output
    assert f"error: --pubkey is not a readable Ed25519 public key ({cls}" in res.output
    no_traceback(res)


@pytest.fixture()
def archived_segment(tmp_path):
    """A real archived segment (the retention apply writes its sidecar), so verify takes the segment branch."""
    data = tmp_path / "data"
    store, _, _ = three_segments(data / "ledger")
    out = store.archive_closed_segments(older_than_days=1, archive_dir=data / "ledger-archive", operator="ops",
                                        data_dir=data, now=datetime.now(timezone.utc) + timedelta(days=3650))
    assert out["archived_segments"] == [1, 2]
    return data / "ledger-archive" / "events-1.jsonl"


@pytest.mark.parametrize("name,cls", KEY_CASES)
def test_verify_segment_with_an_unusable_pubkey_is_exit_2(archived_segment, keys, name, cls):
    res = runner.invoke(cli_app, ["verify", "--path", str(archived_segment), "--pubkey", str(keys[name])])
    assert res.exit_code == 2, res.output
    assert f"error: --pubkey is not a readable Ed25519 public key ({cls}" in res.output
    no_traceback(res)


def test_verify_segment_with_a_good_pubkey_is_unchanged(archived_segment, tmp_path):
    pub = tmp_path / "pub.pem"
    pub.write_text(KEY_PUB, encoding="ascii")
    res = runner.invoke(cli_app, ["verify", "--path", str(archived_segment), "--pubkey", str(pub)])
    no_traceback(res)
    assert "is not a readable" not in res.output


def test_a_good_pubkey_on_verify_is_unchanged(ledger, tmp_path):
    from field_core.signing import generate_keypair

    _, public = generate_keypair()
    pub = tmp_path / "pub.pem"
    pub.write_text(public, encoding="ascii")
    res = runner.invoke(cli_app, ["verify", "--path", str(ledger), "--anchors", str(tmp_path / "a.jsonl"), "--pubkey", str(pub)])
    no_traceback(res)
    assert "is not a readable" not in res.output


@pytest.mark.parametrize("name,cls", [("missing", "FileNotFoundError"), ("bom", "UnicodeDecodeError")])
def test_export_sign_key_error_shows_the_class_only(ledger, tmp_path, keys, name, cls):
    res = runner.invoke(cli_app, ["export", "--path", str(ledger), "--out-dir", str(tmp_path / "x"),
                                  "--sign-key", str(keys[name])])
    assert res.exit_code == 2 and f"error: cannot read --sign-key ({cls})" in res.output
    assert not (tmp_path / "x").exists()
    no_traceback(res)


@pytest.mark.parametrize("name,cls", [("missing", "FileNotFoundError"), ("bom", "UnicodeDecodeError")])
def test_verify_export_pubkey_error_shows_the_class_only(tmp_path, keys, name, cls):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    res = runner.invoke(cli_app, ["verify-export", str(bundle), "--pubkey", str(keys[name])])
    assert res.exit_code == 2 and f"error: cannot read --pubkey ({cls})" in res.output
    no_traceback(res)


def raise_on_append(monkeypatch, exc):
    def append(self, *a, **k):
        raise exc

    monkeypatch.setattr(store_module.LedgerStore, "append", append)


def test_append_on_a_busy_store_is_exit_4(ledger, monkeypatch):
    raise_on_append(monkeypatch, LedgerBusy("could not take the writer lock"))
    res = runner.invoke(cli_app, ["append", "action", "--path", str(ledger)])
    assert res.exit_code == 4 and "BUSY — could not take the writer lock; retry" in res.output
    no_traceback(res)


def test_append_on_an_unreadable_store_is_exit_4_without_retry(ledger, monkeypatch):
    raise_on_append(monkeypatch, LedgerBusy(UNREADABLE_PREFIX + "permission denied"))
    res = runner.invoke(cli_app, ["append", "action", "--path", str(ledger)])
    assert res.exit_code == 4 and "UNREADABLE" in res.output and "retry" not in res.output
    no_traceback(res)


def test_append_on_a_corrupt_store_is_exit_1_in_one_line(ledger, monkeypatch):
    raise_on_append(monkeypatch, LedgerCorrupt("segment 1 does not reconcile"))
    res = runner.invoke(cli_app, ["append", "action", "--path", str(ledger)])
    assert res.exit_code == 1 and res.output.strip() == "error: ledger corrupt: segment 1 does not reconcile"
    no_traceback(res)


def test_append_still_succeeds_and_still_refuses_a_bad_payload(ledger):
    assert runner.invoke(cli_app, ["append", "action", "--path", str(ledger)]).exit_code == 0
    res = runner.invoke(cli_app, ["append", "action", "--path", str(ledger), "--payload", "[1]"])
    assert res.exit_code == 2 and "bad --payload" in res.output
