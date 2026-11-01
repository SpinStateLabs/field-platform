"""C-1072 (reviewer C-1052, Lane 15): parse, verify and window edges that no test pinned.

F-1  ``parse_pack_json`` of a deeply nested input is a named ``PackVerificationError`` (``attest verify`` prints a
     ``FAILED`` line and exits 1), never a RecursionError traceback.
F-5  ``verify_pack`` with a key that is not a string is a named ``PackVerificationError``, never an AttributeError.
Four survivors of the reviewer's mutants: ``signed`` as 1 or "true" is UNSIGNED, a pack with no signature or
fingerprint gets the named refusal, a whitespace-padded bound and a lower-case ``z`` are accepted.
(F-2, F-3 and F-4 are Don's rulings and are not touched here.)"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from attestation_reporter.cli import app as cli_app
from attestation_reporter.signing import PackVerificationError, parse_pack_json, verify_pack
from attestation_reporter.window import InvalidWindow, normalise_bound

runner = CliRunner()


@pytest.fixture(scope="module")
def pub_pem() -> str:
    key = Ed25519PrivateKey.generate().public_key()
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")


def _signed_shape(**over) -> dict:
    """A pack that says it is signed and names every field the early guards read; the signature is not real."""
    raw = {"signed": True, "signature": "AAAA", "key_fingerprint": "ab" * 32, "signer": "Don Hagell"}
    raw.update(over)
    return raw


# --- F-1: a deeply nested input -------------------------------------------------------------------------------------

DEEP = [("[" * 100_000), '{"signed": true, "x": ' + "[" * 20_000]


@pytest.mark.parametrize("text", DEEP, ids=["array-100000", "pack-shaped-20000"])
def test_a_deeply_nested_input_is_a_named_refusal_not_a_recursion_error(text):
    with pytest.raises(PackVerificationError, match="nested"):
        parse_pack_json(text)


def test_a_moderately_nested_balanced_input_still_parses():
    assert parse_pack_json("[" * 500 + "]" * 500) is not None


def test_verify_prints_a_failed_line_and_exits_1_on_a_deeply_nested_pack(tmp_path, pub_pem):
    pack, pub = tmp_path / "deep.json", tmp_path / "pub.pem"
    pack.write_text("[" * 100_000, encoding="utf-8")
    pub.write_text(pub_pem, encoding="ascii")
    result = runner.invoke(cli_app, ["verify", str(pack), "--pubkey", str(pub)])
    assert result.exit_code == 1
    assert "FAILED" in result.stderr and "nested" in result.stderr
    assert "Traceback" not in result.stderr and not isinstance(result.exception, RecursionError)


# --- F-5: a key that is not a string ---------------------------------------------------------------------------------

@pytest.mark.parametrize("key", [None, 7, b"-----BEGIN PUBLIC KEY-----", ["pem"]], ids=["none", "int", "bytes", "list"])
def test_a_supplied_key_that_is_not_a_string_is_a_named_refusal(key):
    with pytest.raises(PackVerificationError, match="supplied public key is not usable"):
        verify_pack(_signed_shape(), key)


# --- survivors: signing.py `signed is not True`, and the signature/fingerprint guard ----------------------------------

@pytest.mark.parametrize("signed", [1, "true", "yes", [True], {"a": 1}, 1.0], ids=repr)
def test_only_the_boolean_true_counts_as_signed(signed, pub_pem):
    with pytest.raises(PackVerificationError, match="UNSIGNED"):
        verify_pack(_signed_shape(signed=signed), pub_pem)


@pytest.mark.parametrize("over", [
    {"signature": None}, {"signature": ""}, {"signature": 7},
    {"key_fingerprint": None}, {"key_fingerprint": ""}, {"key_fingerprint": ["ab"]},
], ids=repr)
def test_a_signed_pack_without_a_usable_signature_or_fingerprint_gets_the_named_refusal(over, pub_pem):
    with pytest.raises(PackVerificationError, match="no signature or key_fingerprint"):
        verify_pack(_signed_shape(**over), pub_pem)


def test_a_signed_pack_missing_both_fields_gets_the_named_refusal_not_a_type_error(pub_pem):
    raw = _signed_shape()
    del raw["signature"], raw["key_fingerprint"]
    with pytest.raises(PackVerificationError, match="no signature or key_fingerprint"):
        verify_pack(raw, pub_pem)


# --- survivors: window.py bounds ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("padded, clean", [
    ("  2026-10-01  ", "2026-10-01"),
    ("\t2026-10-01\n", "2026-10-01"),
    (" 2026-10-01T12:30:00Z ", "2026-10-01T12:30:00Z"),
    ("\n2026-10-01T12:30:00+02:00\t", "2026-10-01T12:30:00+02:00"),
])
@pytest.mark.parametrize("end", [False, True])
def test_a_whitespace_padded_bound_is_read_as_the_clean_bound(padded, clean, end):
    assert normalise_bound("since", padded, end=end) == normalise_bound("since", clean, end=end)


@pytest.mark.parametrize("end", [False, True])
def test_a_lower_case_z_is_utc_like_the_upper_case_z(end):
    lower = normalise_bound("until", "2026-10-01T12:30:00z", end=end)
    assert lower == normalise_bound("until", "2026-10-01T12:30:00Z", end=end)
    assert lower == datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("text", ["", "   ", "\t\n"])
def test_a_blank_bound_is_still_refused(text):
    with pytest.raises(InvalidWindow):
        normalise_bound("since", text, end=False)


# --- C-1089: the same refusal on every interpreter and platform -------------------------------------------------------
# CI (Linux, Python 3.14) answered json.JSONDecodeError "Expecting value" at the END of a 100000-deep unterminated
# input instead of RecursionError: the decoder's depth limit depends on the version and on the C stack, so the nesting
# is bounded by a scan BEFORE json.loads (MAX_JSON_DEPTH), and the decoder is never reached for deep input.

from attestation_reporter import signing as _signing  # noqa: E402


@pytest.mark.parametrize("text", [
    "[" * 1001, "{\"a\":" * 1001, "[" * 100_000, "[{\"a\":" * 600,
    '{"signed": true, "x": ' + "[" * 20_000,
], ids=["array-1001", "object-1001", "array-100000", "mixed-1200", "pack-shaped-20000"])
def test_a_nesting_over_the_bound_is_refused_before_the_decoder_runs(text, monkeypatch):
    def decoder_must_not_run(*a, **k):
        raise AssertionError("json.loads was called for an input nested past MAX_JSON_DEPTH")

    monkeypatch.setattr(_signing.json, "loads", decoder_must_not_run)
    with pytest.raises(PackVerificationError, match="nested"):
        parse_pack_json(text)


def test_the_bound_is_exactly_max_json_depth():
    assert _signing.MAX_JSON_DEPTH == 1000
    assert _signing._json_depth_exceeds("[" * 1000, 1000) is False
    assert _signing._json_depth_exceeds("[" * 1001, 1000) is True
    assert _signing._json_depth_exceeds("[" * 3, 2) is True and _signing._json_depth_exceeds("[" * 2, 2) is False


def test_brackets_inside_strings_do_not_count_and_escapes_are_honoured():
    assert _signing._json_depth_exceeds('"' + "[" * 5000 + '"', 10) is False
    assert _signing._json_depth_exceeds('{"a": "' + "{" * 5000 + '"}', 10) is False
    assert _signing._json_depth_exceeds('{"a": "\\"' + "[" * 5000 + '"}', 10) is False      # an escaped quote
    assert _signing._json_depth_exceeds('{"a": "\\\\" , "b": ' + "[" * 11, 10) is True       # escaped backslash, then real
    assert parse_pack_json('{"a": "' + "[" * 5000 + '"}') == {"a": "[" * 5000}


def test_depth_is_the_deepest_point_not_the_total_count():
    assert _signing._json_depth_exceeds("[]" * 5000, 3) is False
    assert _signing._json_depth_exceeds("[[],[],[[]]]", 3) is False and _signing._json_depth_exceeds("[[],[],[[]]]", 2) is True


def test_a_real_sized_pack_is_unaffected_by_the_bound():
    pack = {"signed": True, "sections": [{"metrics": [{"name": "n", "value": 1}]}], "x": {"y": {"z": [1, 2, 3]}}}
    assert parse_pack_json(__import__("json").dumps(pack)) == pack
