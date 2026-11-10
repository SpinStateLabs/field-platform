"""S9-17: a signer is a name you can SEE on one line, as an org is (S4-17).

``checked_signer`` refuses a non-str or blank value, more than 200 characters after strip, and any Cc, Cf, Zl, Zp or Cs
character, with fixed text that never echoes the value. It is applied in ``sign_pack`` (before anything is signed), in
``served_signing_from_env`` (a bad FIELD_ATTEST_SIGNER is the existing ``error`` state: packs stay UNSIGNED) and in
``attest render --signer`` (exit 2). ``attest verify`` still verifies a pack whose signer already holds such characters
(signed before this rule) and prints that signer escaped. Every value is made up."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from attestation_reporter import org as org_module
from attestation_reporter.api import create_app
from attestation_reporter.cli import app as cli_app
from attestation_reporter.engine import BoardPack
from attestation_reporter.org import InvalidSigner, checked_signer
from attestation_reporter.signing import SIGN_KEY_ENV, SIGNER_ENV, served_signing_from_env, sign_pack, signer_public_pem
from field_core.signing import generate_keypair, key_fingerprint, sign_manifest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pre_f4"
MARK = "MARKER-7c1e"
BAD = {
    "newline": f"Don{chr(10)}{MARK}",
    "esc": f"Don\x1b[31m{MARK}",
    "bidi": f"Don\u202e{MARK}",
    "line-separator": f"Don\u2028{MARK}",
    "zero-width": f"Don\u200b{MARK}",
    "201-chars": "x" * 201,
    "lone-surrogate": f"Don\ud800{MARK}",
}
runner = CliRunner()


@pytest.fixture()
def keys(tmp_path):
    private, public = generate_keypair()
    key = tmp_path / "sign.pem"
    key.write_text(private, encoding="ascii")
    return private, public, key


def unsigned() -> BoardPack:
    raw = json.loads((FIXTURE / "board-pack.json").read_text(encoding="utf-8"))
    raw.update(signed=False, signer=None, signed_at=None, key_fingerprint=None, signature=None)
    raw.pop("signed_via", None)
    return BoardPack.model_validate(raw)


# -- the rule ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [None, 5, [], "", "   ", "\t\n"], ids=repr)
def test_a_non_string_or_blank_signer_is_refused(value):
    with pytest.raises(InvalidSigner, match="blank refused"):
        checked_signer(value)


@pytest.mark.parametrize("name", list(BAD))
def test_a_bad_signer_is_refused_with_text_that_never_echoes_it(name):
    with pytest.raises(InvalidSigner) as exc:
        checked_signer(BAD[name])
    assert MARK not in str(exc.value) and "\x1b" not in str(exc.value)


def test_the_limit_is_200_after_strip_and_the_value_returned_is_stripped():
    assert checked_signer("  " + "x" * 200 + "\t") == "x" * 200
    assert checked_signer("  Don Hagell  ") == "Don Hagell"
    assert checked_signer("Zoë Müller 田中") == "Zoë Müller 田中"
    assert org_module.MAX_SIGNER_CHARS == 200


def test_an_invalid_signer_is_a_value_error_so_existing_callers_still_catch_it():
    assert issubclass(InvalidSigner, ValueError)


# -- sign_pack -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", list(BAD))
def test_sign_pack_refuses_a_bad_signer_before_signing(keys, name):
    with pytest.raises(InvalidSigner):
        sign_pack(unsigned(), BAD[name], keys[0])


def test_sign_pack_signs_the_stripped_value(keys):
    assert sign_pack(unsigned(), "  Don Hagell \n", keys[0]).signer == "Don Hagell"


# -- served --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", list(BAD))
def test_a_bad_served_signer_is_the_error_state_and_health_never_echoes_it(keys, monkeypatch, name):
    env = {SIGNER_ENV: BAD[name], SIGN_KEY_ENV: str(keys[2])}
    served = served_signing_from_env(env)
    assert served.status == "error" and served.signer is None and served.private_key_pem is None
    assert MARK not in served.key_error and "\x1b" not in served.key_error and SIGNER_ENV in served.key_error
    try:  # a lone surrogate cannot be placed in a process environment (the OS refuses it): the dict form above covers it
        for k, v in env.items():
            monkeypatch.setenv(k, v)
    except UnicodeEncodeError:
        assert name == "lone-surrogate"
        return
    body = TestClient(create_app()).get("/health").json()
    assert body["signing"] == "error" and body["signer"] is None and MARK not in json.dumps(body)


def test_a_good_served_signer_is_signed_under_stripped(keys):
    served = served_signing_from_env({SIGNER_ENV: "  Don Hagell  ", SIGN_KEY_ENV: str(keys[2])})
    assert served.status == "on" and served.signer == "Don Hagell"


# -- render --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", list(BAD))
def test_render_refuses_a_bad_signer_with_exit_2_before_anything_is_written(keys, tmp_path, name):
    out = tmp_path / "out"
    res = runner.invoke(cli_app, ["render", "--signer", BAD[name], "--sign-key", str(keys[2]), "--out", str(out)])
    assert res.exit_code == 2 and not out.exists()
    assert MARK not in res.output and "\x1b" not in res.output


def test_render_still_refuses_a_blank_signer_with_the_old_text(keys, tmp_path):
    res = runner.invoke(cli_app, ["render", "--signer", "  ", "--sign-key", str(keys[2]), "--out", str(tmp_path / "o")])
    assert res.exit_code == 2 and "blank refused" in res.output


# -- verify --------------------------------------------------------------------------------------------------------------
def test_verify_still_accepts_the_pre_f4_fixture():
    res = runner.invoke(cli_app, ["verify", str(FIXTURE / "board-pack.json"), "--pubkey", str(FIXTURE / "signer.pub.pem")])
    assert res.exit_code == 0 and "Don Hagell (pre-F4 fixture)" in res.output


def test_verify_prints_an_old_pack_signer_escaped_when_it_holds_control_characters(keys, tmp_path):
    private, public, _ = keys
    raw = json.loads((FIXTURE / "board-pack.json").read_text(encoding="utf-8"))
    raw.pop("signature")
    raw["signer"] = "Don\x1b[31m\u202eEVIL\nlines"
    raw["key_fingerprint"] = key_fingerprint(signer_public_pem(private))
    raw["signature"] = sign_manifest(raw, private)
    pack_path, pub_path = tmp_path / "board-pack.json", tmp_path / "pub.pem"
    pack_path.write_text(json.dumps(raw), encoding="utf-8")
    pub_path.write_text(public, encoding="ascii")
    res = runner.invoke(cli_app, ["verify", str(pack_path), "--pubkey", str(pub_path)])
    assert res.exit_code == 0, res.output
    assert "\x1b" not in res.output and "\u202e" not in res.output and "EVIL\nlines" not in res.output
    assert "\\x1b" in res.output and "\\u202e" in res.output and "\\n" in res.output
