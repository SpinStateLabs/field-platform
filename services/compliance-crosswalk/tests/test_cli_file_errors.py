"""S6-23: ``crosswalk run | suggest | pack`` with a missing or invalid manifest or an unwritable ``--markdown`` /
``--out-md`` / ``--out-json`` path: one stderr line, exit 2, no traceback, nothing written; output paths are checked BEFORE
any network call, and ``pack`` replaces its two files only after both were written."""

from __future__ import annotations

import os

import pytest
import yaml
from typer.testing import CliRunner

from compliance_crosswalk import cli as cli_mod
from tests.test_signer_sanitise_c252 import resolved_manifest

runner = CliRunner()


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))      # the stale store
    monkeypatch.setenv("CROSSWALK_SUGGEST", "mock")


@pytest.fixture()
def good(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(resolved_manifest(), sort_keys=False), encoding="utf-8")
    return str(p)


def invoke(*args):
    r = runner.invoke(cli_mod.app, list(args))
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
    assert "Traceback" not in r.output
    return r


def one_line_error(r, needle):
    assert r.exit_code == 2, r.output
    assert r.output.count("\n") == 1 and r.output.startswith("error: ") and needle in r.output, r.output


def bad_manifests(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    nonutf = tmp_path / "nonutf.yaml"
    nonutf.write_bytes(b"agent:\n  name: \xff\xfe\n")
    inv = tmp_path / "invalid.yaml"
    inv.write_text("a: [unclosed\n", encoding="utf-8")
    lst = tmp_path / "list.yaml"
    lst.write_text("- 1\n- 2\n", encoding="utf-8")
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    return {"missing": str(tmp_path / "nope.yaml"), "directory": str(d), "non-utf8": str(nonutf),
            "invalid-yaml": str(inv), "yaml-list": str(lst), "empty": str(empty), "nul": "a\x00b.yaml"}


@pytest.mark.parametrize("kind", ["missing", "directory", "non-utf8", "invalid-yaml", "yaml-list", "empty", "nul"])
@pytest.mark.parametrize("cmd", ["run", "suggest", "pack"])
def test_a_bad_manifest_is_one_line_exit_2_in_every_command(tmp_path, kind, cmd):
    path = bad_manifests(tmp_path)[kind]
    args = {"run": ["run", path], "suggest": ["suggest", path], "pack": ["pack", path, "--signer", "Ann Lee"]}[cmd]
    r = invoke(*args)
    one_line_error(r, "cannot read the manifest")
    assert "nothing written" in r.output


def test_the_message_never_quotes_the_file(tmp_path):
    p = tmp_path / "secret.yaml"
    p.write_text("key: [SECRETTEXT\n", encoding="utf-8")
    r = invoke("run", str(p))
    assert "SECRETTEXT" not in r.output and "YAMLError" in r.output or "ParserError" in r.output


# ---- outputs ------------------------------------------------------------------------------------------------------------

def test_run_markdown_into_a_missing_directory_or_at_a_directory_or_with_nul(good, tmp_path):
    for target in (str(tmp_path / "nope" / "r.md"), str(tmp_path), "a\x00b.md"):
        one_line_error(invoke("run", good, "--markdown", target), "--markdown")


@pytest.mark.parametrize("opt", ["--out-md", "--out-json"])
def test_pack_outputs_that_cannot_be_written_are_refused_before_any_network_call(good, tmp_path, monkeypatch, opt):
    calls = []
    import compliance_crosswalk.api as api
    monkeypatch.setattr(api, "collect_evidence", lambda agent_id: calls.append(agent_id))
    for target in (str(tmp_path / "nope" / "p.out"), str(tmp_path), "a\x00b"):
        r = invoke("pack", good, "--signer", "Ann Lee", "--agent-id", "a1", opt, target)
        one_line_error(r, opt)
    assert calls == []                                          # no evidence collection happened


def test_a_read_only_directory_is_refused(good, tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        if os.access(ro, os.W_OK):
            pytest.skip("running as a user that ignores permissions")
        one_line_error(invoke("pack", good, "--signer", "Ann Lee", "--out-json", str(ro / "p.json")), "--out-json")
    finally:
        ro.chmod(0o700)


def test_a_failing_second_output_leaves_no_half_pack(good, tmp_path, monkeypatch):
    """--out-json cannot be written (its name is a directory only discovered at write time): neither file may remain."""
    md, js = tmp_path / "p.md", tmp_path / "p.json"
    real = cli_mod.Path.write_text

    def flaky(self, text, *a, **k):
        if self.name.startswith(".p.json"):
            raise OSError("disk full")
        return real(self, text, *a, **k)

    monkeypatch.setattr(cli_mod.Path, "write_text", flaky)
    r = invoke("pack", good, "--signer", "Ann Lee", "--out-md", str(md), "--out-json", str(js))
    one_line_error(r, "--out-json")
    assert not md.exists() and not js.exists()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".p.")] == []     # no temp left behind


# ---- the good path is unchanged -------------------------------------------------------------------------------------------

def test_run_and_pack_good_paths_write_their_files(good, tmp_path):
    r = invoke("run", good, "--markdown", str(tmp_path / "r.md"))
    assert r.exit_code in (0, 1)                                 # 1 only when the manifest is invalid, not a file error
    assert (tmp_path / "r.md").read_text(encoding="utf-8").startswith("# Compliance crosswalk")
    r = invoke("pack", good, "--signer", "Ann Lee", "--out-md", str(tmp_path / "p.md"), "--out-json", str(tmp_path / "p.json"))
    assert r.exit_code == 0, r.output
    assert (tmp_path / "p.md").read_text(encoding="utf-8").startswith("# Evidence Pack")
    assert '"signer": "Ann Lee"' in (tmp_path / "p.json").read_text(encoding="utf-8")
    assert "pack written to" in r.output and "pack json written to" in r.output
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_pack_without_outputs_prints_the_markdown(good):
    r = invoke("pack", good, "--signer", "Ann Lee")
    assert r.exit_code == 0 and r.output.startswith("# Evidence Pack")


def test_suggest_good_path_runs(good):
    r = invoke("suggest", good)
    assert r.exit_code == 0 and "unmapped path(s)" in r.output
