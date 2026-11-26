"""S10-29: a registry or token file saved by Windows PowerShell 5.1 (`>`, Out-File, Set-Content) carries a UTF-8 BOM or
is UTF-16. A BOM is accepted (the same as phase_g_check.py, estate_probe.py, renew_token.py); UTF-16 is refused with a
line that names the cause, not `JSONDecodeError`. Refusals keep the contract: exit 2, nothing written, type-only text.
"""
from __future__ import annotations

import codecs
import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))   # reuse the helpers of the base test file
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_doa_roster as gen  # noqa: E402
from test_generate_doa_roster import estate, manifest, record, rows, token  # noqa: E402,F401


def _main(tmp_path: Path, registry: Path, *extra: str):
    out = tmp_path / "out" / "doa-roster.yaml"
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        code = gen.main(["--registry", str(registry), "--manifests", str(tmp_path / "manifests"),
                         "--out", str(out), *extra])
    return code, so.getvalue(), se.getvalue(), out


def _save(path: Path, obj, encoding: str, bom: bytes = b"") -> Path:
    path.write_bytes(bom + json.dumps(obj).encode(encoding))
    return path


def _plain(tmp_path, estate):
    reg = _save(tmp_path / "plain.json", estate, "utf-8")
    tok = _save(tmp_path / "plain-tokens.json", [token("inv", "Token Only Grantor")], "utf-8")
    code, _, err, out = _main(tmp_path, reg, "--tokens", str(tok))
    assert code == 0, err
    return out.read_text(encoding="utf-8").split("\n", 3)[3]   # the roster body, without the generated header


def test_a_bom_registry_and_tokens_give_the_same_roster_as_no_bom(tmp_path, estate):
    want = _plain(tmp_path, estate)
    reg = _save(tmp_path / "bom.json", estate, "utf-8", codecs.BOM_UTF8)
    tok = _save(tmp_path / "bom-tokens.json", [token("inv", "Token Only Grantor")], "utf-8", codecs.BOM_UTF8)
    code, _, err, out = _main(tmp_path, reg, "--tokens", str(tok))
    assert code == 0, err
    assert out.read_text(encoding="utf-8").split("\n", 3)[3] == want
    assert "Token Only Grantor" in rows(out)


def test_a_bom_registry_alone_is_accepted(tmp_path, estate):
    reg = _save(tmp_path / "bom.json", estate, "utf-8", codecs.BOM_UTF8)
    code, _, err, out = _main(tmp_path, reg)
    assert code == 0, err
    assert sorted(rows(out)) == ["Don Co", "Jane Doe"]


@pytest.mark.parametrize("enc,bom", [("utf-16-le", codecs.BOM_UTF16_LE), ("utf-16-be", codecs.BOM_UTF16_BE)])
def test_a_utf16_registry_is_refused_by_name(tmp_path, estate, enc, bom):
    reg = _save(tmp_path / "ps.json", estate, enc, bom)
    code, _, err, out = _main(tmp_path, reg)
    assert code == 2
    assert "--registry" in err and "UTF-16" in err and "re-save as UTF-8" in err
    assert "JSONDecodeError" not in err and "UnicodeDecodeError" not in err
    assert not out.exists()


@pytest.mark.parametrize("enc,bom", [("utf-16-le", codecs.BOM_UTF16_LE), ("utf-16-be", codecs.BOM_UTF16_BE)])
def test_a_utf16_tokens_file_is_refused_by_name(tmp_path, estate, enc, bom):
    reg = _save(tmp_path / "ok.json", estate, "utf-8")
    tok = _save(tmp_path / "ps-tokens.json", [token("inv", "G")], enc, bom)
    code, _, err, out = _main(tmp_path, reg, "--tokens", str(tok))
    assert code == 2
    assert "--tokens" in err and "UTF-16" in err and "re-save as UTF-8" in err
    assert "JSONDecodeError" not in err and "UnicodeDecodeError" not in err
    assert not out.exists()


def test_a_bom_on_a_non_list_is_still_refused(tmp_path, estate):
    reg = _save(tmp_path / "bom-obj.json", {"agent_id": "x"}, "utf-8", codecs.BOM_UTF8)
    code, _, err, out = _main(tmp_path, reg)
    assert code == 2 and "expected a JSON list" in err
    assert not out.exists()


def test_a_bom_on_a_non_list_tokens_file_is_still_refused(tmp_path, estate):
    reg = _save(tmp_path / "ok.json", estate, "utf-8")
    tok = _save(tmp_path / "t.json", {"token_id": "x"}, "utf-8", codecs.BOM_UTF8)
    code, _, err, out = _main(tmp_path, reg, "--tokens", str(tok))
    assert code == 2 and "expected a JSON list" in err
    assert not out.exists()


def test_a_bom_followed_by_garbage_is_still_the_type_only_message(tmp_path, estate):
    reg = tmp_path / "bad.json"
    reg.write_bytes(codecs.BOM_UTF8 + b"SECRETISH not json")
    code, _, err, _ = _main(tmp_path, reg)
    assert code == 2 and "not a readable JSON file (JSONDecodeError)" in err
    assert "SECRETISH" not in err


def test_a_file_that_only_looks_like_utf16_is_not_misnamed(tmp_path, estate):
    """Two bytes FF FE are the UTF-16 mark only at the very start; plain UTF-8 JSON never starts with them."""
    reg = _save(tmp_path / "ok.json", estate, "utf-8")
    code, _, err, _ = _main(tmp_path, reg)
    assert code == 0, err
    assert "UTF-16" not in err


@pytest.mark.parametrize("flag", ["--registry", "--tokens"])
def test_an_unreadable_path_is_the_type_only_refusal(tmp_path, estate, flag):
    ok = _save(tmp_path / "ok.json", estate, "utf-8")
    bad = tmp_path / "a-directory"
    bad.mkdir()
    extra = ("--tokens", str(bad)) if flag == "--tokens" else ()
    code, _, err, out = _main(tmp_path, bad if flag == "--registry" else ok, *extra)
    assert code == 2 and f"{flag} " in err and "not a readable JSON file (" in err
    assert not out.exists()


def test_non_utf8_bytes_are_the_type_only_refusal(tmp_path, estate):
    reg = tmp_path / "latin.json"
    reg.write_bytes(b"[\x80\x81]")
    code, _, err, _ = _main(tmp_path, reg)
    assert code == 2 and "not a readable JSON file (UnicodeDecodeError)" in err
