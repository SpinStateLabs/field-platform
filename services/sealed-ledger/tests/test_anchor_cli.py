"""S5-9: ``ledger anchor`` and ``ledger rotate --anchors`` fail with one stderr line and a fixed exit code, never a
traceback and never key text (the guard ``ledger export`` already has for --sign-key)."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import rsa
from typer.testing import CliRunner

from field_core.signing import generate_keypair
from sealed_ledger.anchors import verify_anchors
from sealed_ledger.cli import app
from sealed_ledger.store import LedgerBusy, LedgerCorrupt, LedgerStore

runner = CliRunner()


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_LEDGER_URL", raising=False)
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    for i in range(3):
        s.append(f"t.{i}", {"i": i})
    return s, p


def keypair(tmp_path):
    priv, pub = generate_keypair()
    (tmp_path / "k.pem").write_text(priv)
    (tmp_path / "pub.pem").write_text(pub)
    return tmp_path / "k.pem", tmp_path / "pub.pem"


def anchor(p, anchors, *extra):
    return runner.invoke(app, ["anchor", "--path", str(p), "--anchors", str(anchors), *extra])


def clean(r):
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
    assert "Traceback" not in r.output


def test_happy_unsigned_writes_one_parseable_line(ledger, tmp_path):
    s, p = ledger
    r = anchor(p, tmp_path / "a.jsonl")
    assert r.exit_code == 0, r.output
    lines = (tmp_path / "a.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["chain_length"] == 3


def test_signed_anchor_verifies(ledger, tmp_path):
    s, p = ledger
    k, pub = keypair(tmp_path)
    assert anchor(p, tmp_path / "a.jsonl", "--key", str(k)).exit_code == 0
    assert verify_anchors(s, tmp_path / "a.jsonl", public_key_pem=pub.read_text()).ok


def test_missing_key_exits_2(ledger, tmp_path):
    r = anchor(ledger[1], tmp_path / "a.jsonl", "--key", str(tmp_path / "nope.pem"))
    clean(r); assert r.exit_code == 2 and "--key" in r.output and not (tmp_path / "a.jsonl").exists()


def test_directory_as_key_exits_2(ledger, tmp_path):
    r = anchor(ledger[1], tmp_path / "a.jsonl", "--key", str(tmp_path))
    clean(r); assert r.exit_code == 2


def test_non_ascii_key_exits_2_without_its_bytes(ledger, tmp_path):
    k = tmp_path / "k.pem"; k.write_bytes(b"-----BEGIN PRIVATE KEY-----\n\xc3\xa9SECRETBYTES\n")
    r = anchor(ledger[1], tmp_path / "a.jsonl", "--key", str(k))
    clean(r); assert r.exit_code == 2 and "SECRETBYTES" not in r.output and "UnicodeDecodeError" in r.output


def test_garbage_pem_exits_2_without_its_text(ledger, tmp_path):
    k = tmp_path / "k.pem"; k.write_text("SECRETGARBAGE not a pem")
    r = anchor(ledger[1], tmp_path / "a.jsonl", "--key", str(k))
    clean(r); assert r.exit_code == 2 and "SECRETGARBAGE" not in r.output and not (tmp_path / "a.jsonl").exists()


def test_rsa_key_exits_2(ledger, tmp_path):
    pem = rsa.generate_private_key(65537, 2048).private_bytes(
        ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()).decode()
    k = tmp_path / "k.pem"; k.write_text(pem)
    r = anchor(ledger[1], tmp_path / "a.jsonl", "--key", str(k))
    clean(r); assert r.exit_code == 2 and "Ed25519" in r.output


def test_anchors_path_is_a_directory_exits_1_naming_it(ledger, tmp_path):
    d = tmp_path / "adir"; d.mkdir()
    r = anchor(ledger[1], d)
    clean(r); assert r.exit_code == 1 and str(d) in r.output


def test_ledger_corrupt_exits_1(ledger, tmp_path, monkeypatch):
    monkeypatch.setattr("sealed_ledger.anchors.write_anchor", lambda *a, **k: (_ for _ in ()).throw(LedgerCorrupt("bad")))
    r = anchor(ledger[1], tmp_path / "a.jsonl")
    clean(r); assert r.exit_code == 1 and "corrupt" in r.output


def test_ledger_busy_exits_4(ledger, tmp_path, monkeypatch):
    monkeypatch.setattr("sealed_ledger.anchors.write_anchor", lambda *a, **k: (_ for _ in ()).throw(LedgerBusy("busy now")))
    r = anchor(ledger[1], tmp_path / "a.jsonl")
    clean(r); assert r.exit_code == 4 and "BUSY" in r.output


def test_rotate_with_unwritable_anchors_reports_success_then_failure(ledger, tmp_path):
    s, p = ledger
    k, _ = keypair(tmp_path)
    d = tmp_path / "adir"; d.mkdir()
    r = runner.invoke(app, ["rotate", "--offline", "--path", str(p), "--key", str(k), "--operator", "o",
                            "--reason", "r", "--anchors", str(d)])
    clean(r)
    assert r.exit_code == 1
    assert "SUCCEEDED" in r.output and "NOT written" in r.output and str(d) in r.output
    assert r.output.index("{") < r.output.index("SUCCEEDED")        # the RotationResult is printed first


def test_rotate_with_writable_anchors_still_succeeds(ledger, tmp_path):
    s, p = ledger
    k, _ = keypair(tmp_path)
    r = runner.invoke(app, ["rotate", "--offline", "--path", str(p), "--key", str(k), "--operator", "o",
                            "--reason", "r", "--anchors", str(tmp_path / "a.jsonl")])
    assert r.exit_code == 0, r.output
    assert len((tmp_path / "a.jsonl").read_text().splitlines()) == 1
