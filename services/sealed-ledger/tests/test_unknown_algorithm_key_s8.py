"""S8-18 — a key under an unknown algorithm OID is a named refusal, never a traceback.

cryptography raises UnsupportedAlgorithm, which is NOT a ValueError, for a PKCS#8 private key or a
SubjectPublicKeyInfo under an unknown OID (reproduced on cryptography 50.0.2: `export --sign-key`,
`verify-export --pubkey`, `verify --event-pubkey` and `verify-witness --pubkey` were all tracebacks).
The real-PEM tests fail on main; the monkeypatched ones pin the handlers independently of the library."""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from typer.testing import CliRunner

from field_core.signing import generate_keypair
from sealed_ledger import bundle as bundle_mod
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore

runner = CliRunner()


def _der(tag: int, body: bytes) -> bytes:
    n = len(body)
    return bytes([tag]) + (bytes([n]) if n < 128 else bytes([0x81, n])) + body


def unknown_algorithm_pem(kind: str) -> str:
    """A PKCS#8 private key or SubjectPublicKeyInfo under the OID 1.2.3.4.5 (same builder as
    attestation-reporter/tests/test_c4_window_and_signature.py)."""
    oid = _der(0x30, _der(0x06, bytes([0x2A, 0x03, 0x04, 0x05])))
    if kind == "PRIVATE KEY":
        der = _der(0x30, _der(0x02, b"\x00") + oid + _der(0x04, _der(0x04, bytes(32))))
    else:
        der = _der(0x30, oid + _der(0x03, b"\x00" + bytes(32)))
    return f"-----BEGIN {kind}-----\n{base64.encodebytes(der).decode('ascii')}-----END {kind}-----\n"


@pytest.fixture()
def ledger(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    s.append("x.event", {"i": 1})
    return p


@pytest.fixture()
def keys(tmp_path):
    priv, pub = generate_keypair()
    (tmp_path / "good-priv.pem").write_text(priv, encoding="ascii")
    (tmp_path / "good-pub.pem").write_text(pub, encoding="ascii")
    (tmp_path / "bad-priv.pem").write_text(unknown_algorithm_pem("PRIVATE KEY"), encoding="ascii")
    (tmp_path / "bad-pub.pem").write_text(unknown_algorithm_pem("PUBLIC KEY"), encoding="ascii")
    return tmp_path


def _clean_exit(r):
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
    assert "Traceback" not in r.output


def test_the_premise_unknown_oid_private_key_is_not_a_value_error():
    from cryptography.hazmat.primitives import serialization

    with pytest.raises(UnsupportedAlgorithm):
        serialization.load_pem_private_key(unknown_algorithm_pem("PRIVATE KEY").encode(), password=None)


def test_export_sign_key_with_an_unknown_oid_is_exit_2_and_writes_nothing(ledger, keys):
    out = keys / "out"
    r = runner.invoke(cli_app, ["export", "--path", str(ledger), "--out-dir", str(out),
                                "--sign-key", str(keys / "bad-priv.pem")])
    assert r.exit_code == 2, r.output
    _clean_exit(r)
    assert "signing key is not a readable PEM private key (UnsupportedAlgorithm)" in r.output
    assert not out.exists() or not any(out.iterdir())           # nothing written before the key check


def test_export_sign_key_existing_failures_keep_exit_2(ledger, keys):
    garbage = keys / "garbage.pem"
    garbage.write_text("not a key", encoding="ascii")
    r = runner.invoke(cli_app, ["export", "--path", str(ledger), "--out-dir", str(keys / "o2"),
                                "--sign-key", str(garbage)])
    assert r.exit_code == 2 and "signing key is not a readable PEM private key" in r.output
    r = runner.invoke(cli_app, ["export", "--path", str(ledger), "--out-dir", str(keys / "o3"),
                                "--sign-key", str(keys / "good-pub.pem")])
    assert r.exit_code == 2                                       # a public key is not a private key


def test_a_good_key_still_signs_and_verifies(ledger, keys):
    out = keys / "out-ok"
    r = runner.invoke(cli_app, ["export", "--path", str(ledger), "--out-dir", str(out),
                                "--sign-key", str(keys / "good-priv.pem")])
    assert r.exit_code == 0, r.output
    (bundle,) = list(out.iterdir())
    r = runner.invoke(cli_app, ["verify-export", str(bundle), "--pubkey", str(keys / "good-pub.pem")])
    assert r.exit_code == 0, r.output


def test_verify_export_with_an_unknown_oid_public_key_is_a_named_failure(ledger, keys):
    out = keys / "out-signed"
    assert runner.invoke(cli_app, ["export", "--path", str(ledger), "--out-dir", str(out),
                                   "--sign-key", str(keys / "good-priv.pem")]).exit_code == 0
    (bundle,) = list(out.iterdir())
    r = runner.invoke(cli_app, ["verify-export", str(bundle), "--pubkey", str(keys / "bad-pub.pem")])
    assert r.exit_code == 1, r.output
    _clean_exit(r)
    assert "EXPORT FAILED" in r.output and "supplied public key is not usable" in r.output


def _raise_unsupported(*a, **k):
    raise UnsupportedAlgorithm("unknown OID")


def test_verify_export_when_key_fingerprint_raises_unsupported_algorithm(ledger, keys, monkeypatch):
    out = keys / "out-signed2"
    runner.invoke(cli_app, ["export", "--path", str(ledger), "--out-dir", str(out),
                            "--sign-key", str(keys / "good-priv.pem")])
    (bundle,) = list(out.iterdir())
    monkeypatch.setattr(bundle_mod, "key_fingerprint", _raise_unsupported)
    r = runner.invoke(cli_app, ["verify-export", str(bundle), "--pubkey", str(keys / "good-pub.pem")])
    assert r.exit_code == 1, r.output
    _clean_exit(r)
    assert "supplied public key is not usable (UnsupportedAlgorithm)" in r.output


@pytest.mark.parametrize("argv_builder", [
    lambda p, k: ["verify", "--path", str(p), "--event-pubkey", str(k / "good-pub.pem")],
    lambda p, k: ["verify-witness", "--estate", "e", "--events-file", str(p), "--path", str(p),
                  "--pubkey", str(k / "good-pub.pem")],
], ids=["verify --event-pubkey", "verify-witness --pubkey"])
def test_public_key_sites_when_key_fingerprint_raises_unsupported_algorithm(ledger, keys, monkeypatch, argv_builder):
    import field_core.signing as signing

    monkeypatch.setattr(signing, "key_fingerprint", _raise_unsupported)
    r = runner.invoke(cli_app, argv_builder(ledger, keys))
    assert r.exit_code == 2, r.output
    _clean_exit(r)
    assert "is not a readable Ed25519 public key (UnsupportedAlgorithm)" in r.output


@pytest.mark.parametrize("argv_builder", [
    lambda p, k: ["verify", "--path", str(p), "--event-pubkey", str(k / "bad-pub.pem")],
    lambda p, k: ["verify-witness", "--estate", "e", "--events-file", str(p), "--path", str(p),
                  "--pubkey", str(k / "bad-pub.pem")],
], ids=["verify --event-pubkey", "verify-witness --pubkey"])
def test_an_unknown_oid_public_key_file_is_exit_2_on_the_real_library(ledger, keys, argv_builder):
    r = runner.invoke(cli_app, argv_builder(ledger, keys))
    assert r.exit_code == 2, r.output
    _clean_exit(r)
