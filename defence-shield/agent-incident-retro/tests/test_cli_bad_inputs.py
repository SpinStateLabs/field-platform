"""S11-25: the CLI turns bad input files into one `error:` line and exit 1, and never loses a key.

`verify` read the pack, the public key, the report and the sources with no handler (a missing, non-UTF-8 or non-JSON file,
a pack that is not an object: a traceback); `_load_config` raised OSError for a missing --config (not caught by the
`except ValueError` in `scan`) and a TypeError for a JSON list; `keygen --out k --pub k --force` wrote the private PEM and
then overwrote it with the public PEM (the private key silently lost), and a failing --pub write after the private key
was on disk was a traceback.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_incident_retro.cli import app
from agent_incident_retro.synth import generate

runner = CliRunner()


def _clean(r):
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
    assert "Traceback" not in r.output


@pytest.fixture()
def kit(tmp_path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    key, pub = tmp_path / "air.key", tmp_path / "air.pub"
    assert runner.invoke(app, ["keygen", "--out", str(key), "--pub", str(pub)]).exit_code == 0
    out = tmp_path / "out"
    assert runner.invoke(app, ["scan", str(log), "--out", str(out), "--key", str(key)]).exit_code == 2
    return {"log": log, "key": key, "pub": pub, "pack": out / "evidence-pack.json", "report": out / "report.md",
            "tmp": tmp_path}


# -- verify -------------------------------------------------------------------------------------------------------


def _verify(kit, **over):
    args = {"pack": kit["pack"], "pub": kit["pub"], **over}
    argv = ["verify", str(args["pack"]), "--pub", str(args["pub"])]
    if "report" in args:
        argv += ["--report", str(args["report"])]
    for s in args.get("sources", []):
        argv += ["--sources", str(s)]
    return runner.invoke(app, argv)


def test_a_good_verify_is_unchanged(kit):
    r = _verify(kit, report=kit["report"], sources=[kit["log"]])
    assert r.exit_code == 0 and "VERIFIED" in r.output


def test_a_missing_pack_is_one_line_exit_1(kit):
    r = _verify(kit, pack=kit["tmp"] / "no-such-pack.json")
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "error:" in r.stderr and "pack" in r.stderr and "FileNotFoundError" in r.stderr
    assert len([ln for ln in r.stderr.splitlines() if ln.strip()]) == 1


@pytest.mark.parametrize("content,why", [
    (b"\xff\xfe\x00 not utf8 \x80", "UnicodeDecodeError"),
    (b"this is not json", "not valid JSON"),
    (b"", "not valid JSON"),
])
def test_a_corrupt_pack_is_one_line_exit_1(kit, content, why):
    kit["pack"].write_bytes(content)
    r = _verify(kit)
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "error:" in r.stderr and "pack" in r.stderr
    assert len([ln for ln in r.stderr.splitlines() if ln.strip()]) == 1


@pytest.mark.parametrize("text", ["[1, 2]", "null", '"a string"', "42", "true"])
def test_a_pack_that_is_not_an_object_is_exit_1(kit, text):
    kit["pack"].write_text(text, encoding="utf-8")
    r = _verify(kit)
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "not a JSON object" in r.stderr


def test_a_missing_or_corrupt_public_key_is_one_line_exit_1(kit):
    r = _verify(kit, pub=kit["tmp"] / "no-such.pub")
    assert r.exit_code == 1 and "public key" in r.stderr and "FileNotFoundError" in r.stderr
    _clean(r)
    kit["pub"].write_bytes(b"\xff\xfe\x80")
    r = _verify(kit)
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "public key" in r.stderr


def test_a_garbage_public_key_text_is_a_failed_verification_not_a_traceback(kit):
    kit["pub"].write_text("-----BEGIN PUBLIC KEY-----\nnot a key\n-----END PUBLIC KEY-----\n", encoding="utf-8")
    r = _verify(kit)
    assert r.exit_code == 1, r.output
    _clean(r)


def test_a_missing_report_is_one_line_exit_1(kit):
    r = _verify(kit, report=kit["tmp"] / "no-report.md")
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "report" in r.stderr and "FileNotFoundError" in r.stderr


def test_a_missing_source_file_is_one_line_exit_1(kit):
    r = _verify(kit, sources=[kit["tmp"] / "no-such.log"])
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "source" in r.stderr and "FileNotFoundError" in r.stderr


def test_a_directory_as_the_pack_is_one_line_exit_1(kit):
    r = _verify(kit, pack=kit["tmp"])
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "error:" in r.stderr


# -- scan --config ------------------------------------------------------------------------------------------------


def _scan(kit, config):
    return runner.invoke(app, ["scan", str(kit["log"]), "--out", str(kit["tmp"] / "o2"), "--key", str(kit["key"]),
                               "--config", str(config)])


def test_a_missing_config_is_one_line_exit_1(kit):
    r = _scan(kit, kit["tmp"] / "no-config.json")
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "error:" in r.stderr and "--config" in r.stderr and "FileNotFoundError" in r.stderr


@pytest.mark.parametrize("content", [b"\xff\xfe\x80 not utf8", b"not json", b""])
def test_a_non_utf8_or_non_json_config_is_one_line_exit_1(kit, content):
    cfg = kit["tmp"] / "c.json"
    cfg.write_bytes(content)
    r = _scan(kit, cfg)
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "error:" in r.stderr and "--config" in r.stderr


@pytest.mark.parametrize("text", ["[1, 2]", "null", '"s"', "7", "true"])
def test_a_config_that_is_not_an_object_is_one_line_exit_1(kit, text):
    cfg = kit["tmp"] / "c.json"
    cfg.write_text(text, encoding="utf-8")
    r = _scan(kit, cfg)
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "--config must hold a JSON object" in r.stderr


def test_a_good_config_still_works(kit):
    cfg = kit["tmp"] / "c.json"
    cfg.write_text(json.dumps({"session_gap_s": 120}), encoding="utf-8")
    assert _scan(kit, cfg).exit_code == 2


# -- keygen ---------------------------------------------------------------------------------------------------------


def test_keygen_with_out_equal_to_pub_is_refused_and_writes_nothing(tmp_path):
    k = tmp_path / "k"
    r = runner.invoke(app, ["keygen", "--out", str(k), "--pub", str(k)])
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "same" in r.stderr
    assert not k.exists()


@pytest.mark.parametrize("force", [False, True])
def test_keygen_refuses_the_same_file_even_when_it_exists_and_keeps_it(tmp_path, force):
    k = tmp_path / "k"
    k.write_text("PRIVATE-STAYS", encoding="utf-8")
    r = runner.invoke(app, ["keygen", "--out", str(k), "--pub", str(k), *(["--force"] if force else [])])
    assert r.exit_code == 1
    assert k.read_text(encoding="utf-8") == "PRIVATE-STAYS"


def test_keygen_refuses_two_spellings_of_one_path(tmp_path):
    (tmp_path / "sub").mkdir()
    k = tmp_path / "k"
    r = runner.invoke(app, ["keygen", "--out", str(k), "--pub", str(tmp_path / "sub" / ".." / "k"), "--force"])
    assert r.exit_code == 1 and not k.exists()


def test_keygen_refuses_a_symlinked_pub_that_points_at_out(tmp_path):
    k = tmp_path / "k"
    link = tmp_path / "link"
    try:
        link.symlink_to(k)
    except OSError:
        pytest.skip("no symlinks here")
    r = runner.invoke(app, ["keygen", "--out", str(k), "--pub", str(link), "--force"])
    assert r.exit_code == 1 and not k.exists()


def test_keygen_with_two_paths_is_unchanged(tmp_path):
    r = runner.invoke(app, ["keygen", "--out", str(tmp_path / "k"), "--pub", str(tmp_path / "p")])
    assert r.exit_code == 0, r.output
    assert "BEGIN PRIVATE KEY" in (tmp_path / "k").read_text(encoding="utf-8")
    assert "BEGIN PUBLIC KEY" in (tmp_path / "p").read_text(encoding="utf-8")


def test_a_failing_pub_write_after_the_private_key_says_so_in_one_line(tmp_path):
    k = tmp_path / "k"
    blocker = tmp_path / "f"
    blocker.write_text("x", encoding="utf-8")
    r = runner.invoke(app, ["keygen", "--out", str(k), "--pub", str(blocker / "child" / "p")])
    assert r.exit_code == 1, r.output
    _clean(r)
    assert "BEGIN PRIVATE KEY" in k.read_text(encoding="utf-8")          # the private key IS on disk
    err = [ln for ln in r.stderr.splitlines() if ln.strip()]
    assert len(err) == 1 and "private key" in err[0] and "public key" in err[0] and "NotADirectoryError" in err[0]
    assert "BEGIN PUBLIC KEY" in r.stdout                                 # the public half is printed, not lost
    assert "BEGIN PRIVATE KEY" not in r.output
