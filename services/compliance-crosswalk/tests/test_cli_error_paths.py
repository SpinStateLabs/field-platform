"""Scout S-2-16: `crosswalk regwatch clear/set-stale` with an unknown framework or a missing flag, and `run`, `suggest` and
`pack` with a bad manifest path, printed Python tracebacks (`clear` is the CLI-only way to clear a flag on an estate, over
`docker exec`). Each now prints one named line to stderr and exits 2, and writes nothing. FIELD_DATA_DIR points at tmp_path."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from compliance_crosswalk.cli import app
from compliance_crosswalk.mapping import FRAMEWORKS

runner = CliRunner()
KNOWN = sorted(FRAMEWORKS)
FW = KNOWN[0]


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CROSSWALK_SUGGEST", "mock")
    return tmp_path


def invoke(*args):
    return runner.invoke(app, list(args))


def files(d: Path) -> dict[str, bytes]:
    """What the CLI persisted. The empty `.lock` file the store's transaction creates on any clear is not state."""
    return {p.name: p.read_bytes() for p in d.iterdir() if p.is_file() and not p.name.endswith(".lock")}


def assert_clean_refusal(r, *, code=2):
    assert r.exit_code == code, (r.exit_code, r.output)
    assert "Traceback" not in r.output and "Traceback" not in r.stderr
    assert r.exception is None or isinstance(r.exception, SystemExit)
    assert r.stderr.strip().startswith("error:") and len([l for l in r.stderr.strip().splitlines() if l]) == 1


# ---- regwatch set-stale ----------------------------------------------------------------------------------------------

def test_set_stale_with_an_unknown_framework_lists_the_known_ones_and_writes_nothing(data_dir):
    before = files(data_dir)
    r = invoke("regwatch", "set-stale", "no-such-framework", "--reason", "x")
    assert_clean_refusal(r)
    for k in KNOWN:
        assert k in r.stderr
    assert files(data_dir) == before


def test_set_stale_with_a_known_framework_still_works(data_dir):
    r = invoke("regwatch", "set-stale", FW, "--reason", "new edition")
    assert r.exit_code == 0 and f"stale: {FW}" in r.stdout


# ---- regwatch clear --------------------------------------------------------------------------------------------------

def test_clear_with_no_active_flag_says_so_and_writes_nothing(data_dir):
    before = files(data_dir)
    r = invoke("regwatch", "clear", FW, "--reviewed-by", "A. Reviewer")
    assert_clean_refusal(r)
    assert f"no active flag for {FW}" in r.stderr
    assert files(data_dir) == before


def test_clear_with_an_unknown_framework_lists_the_known_ones(data_dir):
    r = invoke("regwatch", "clear", "no-such-framework", "--reviewed-by", "A. Reviewer")
    assert_clean_refusal(r)
    assert all(k in r.stderr for k in KNOWN)


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_clear_with_a_blank_reviewer_is_refused_and_the_flag_stays(data_dir, blank):
    assert invoke("regwatch", "set-stale", FW, "--reason", "r").exit_code == 0
    before = files(data_dir)
    r = invoke("regwatch", "clear", FW, "--reviewed-by", blank)
    assert_clean_refusal(r)
    assert "reviewed-by" in r.stderr
    assert files(data_dir) == before
    assert FW in json.loads(invoke("regwatch", "status").stdout)["active"][0]["framework"]


def test_clear_after_set_stale_still_works_and_a_second_clear_is_refused(data_dir):
    assert invoke("regwatch", "set-stale", FW, "--reason", "r").exit_code == 0
    ok = invoke("regwatch", "clear", FW, "--reviewed-by", "A. Reviewer")
    assert ok.exit_code == 0 and "cleared:" in ok.stdout
    again = invoke("regwatch", "clear", FW, "--reviewed-by", "A. Reviewer")
    assert_clean_refusal(again)
    assert f"no active flag for {FW}" in again.stderr


# ---- run / suggest / pack with a bad manifest ------------------------------------------------------------------------

@pytest.fixture(params=["run", "suggest", "pack"])
def cmd(request):
    base = {"run": ["run"], "suggest": ["suggest"], "pack": ["pack", "--signer", "A. Signer"]}[request.param]
    return lambda path: base[:1] + [str(path)] + base[1:]


def _bad_manifests(tmp_path):
    d = tmp_path / "a-directory"
    d.mkdir()
    (tmp_path / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
    (tmp_path / "scalar.yaml").write_text("just text", encoding="utf-8")
    (tmp_path / "syntax.yaml").write_text("a: [unclosed\nb: {", encoding="utf-8")
    (tmp_path / "binary.yaml").write_bytes(b"\xff\xfe\x00\x80 not utf8")
    (tmp_path / "empty.yaml").write_text("", encoding="utf-8")
    return {"missing": tmp_path / "nope.yaml", "directory": d, "list": tmp_path / "list.yaml",
            "scalar": tmp_path / "scalar.yaml", "syntax": tmp_path / "syntax.yaml",
            "binary": tmp_path / "binary.yaml", "empty": tmp_path / "empty.yaml"}


@pytest.mark.parametrize("kind", ["missing", "directory", "list", "scalar", "syntax", "binary", "empty"])
def test_a_bad_manifest_path_is_one_line_exit_2_and_writes_nothing(data_dir, tmp_path_factory, cmd, kind):
    manifests = _bad_manifests(tmp_path_factory.mktemp("m"))
    before = files(data_dir)
    r = invoke(*cmd(manifests[kind]))
    assert_clean_refusal(r)
    assert "manifest" in r.stderr
    assert files(data_dir) == before
