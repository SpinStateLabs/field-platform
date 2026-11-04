"""S5-3: `registry scan` with a missing, unreadable, non-UTF-8, malformed or oversized input file is exit 2 with one named
`error:` line (stdout empty, no traceback, no file bytes quoted). The n8n file gets the same 1 MiB cap as the other inputs."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.redaction import MAX_SCAN_BYTES

OPTIONS = ["--n8n", "--accounts", "--api-keys", "--secrets-text", "--principals"]
MARK = "SYNTHETIC-MARKER-0123"


def run(tmp_path, *args):
    db = tmp_path / "reg.sqlite3"
    runner = CliRunner(mix_stderr=False) if "mix_stderr" in CliRunner.__init__.__code__.co_varnames else CliRunner()
    return runner.invoke(cli.app, ["scan", *args, "--path", str(db)])


def assert_named_refusal(r, *forbidden):
    assert r.exit_code == 2, (r.exit_code, r.output)
    err = r.stderr if r.stderr_bytes is not None else r.output
    assert "Traceback" not in err and "Traceback" not in r.output
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("error:"), err
    assert r.stdout.strip() == ""
    for f in forbidden:
        assert f not in err


@pytest.mark.parametrize("opt", OPTIONS)
def test_a_missing_file_is_a_named_exit_2(tmp_path, opt):
    # --principals alone scans nothing: pair it with a real --api-keys file
    extra = []
    if opt == "--principals":
        keys = tmp_path / "k.csv"
        keys.write_text("key_name,owner,service,created,last_used\n", encoding="utf-8")
        extra = ["--api-keys", str(keys)]
    r = run(tmp_path, opt, str(tmp_path / "does-not-exist.txt"), *extra)
    assert_named_refusal(r)
    assert "does-not-exist.txt" in r.stderr and "cannot be read" in r.stderr


@pytest.mark.parametrize("opt", OPTIONS[1:])
def test_a_directory_is_a_named_exit_2(tmp_path, opt):
    d = tmp_path / "adir"
    d.mkdir()
    extra = []
    if opt == "--principals":
        keys = tmp_path / "k.csv"
        keys.write_text("key_name,owner,service,created,last_used\n", encoding="utf-8")
        extra = ["--api-keys", str(keys)]
    assert_named_refusal(run(tmp_path, opt, str(d), *extra))


def test_a_binary_n8n_file_is_exit_2_and_quotes_no_bytes(tmp_path):
    f = tmp_path / "wf.json"
    f.write_bytes(MARK.encode() + b"\xff\xfe")
    r = run(tmp_path, "--n8n", str(f))
    assert_named_refusal(r, MARK)
    assert "not UTF-8 text" in r.stderr


@pytest.mark.parametrize("body", ["{not json", "", "[1, 2", MARK + " {"])
def test_invalid_json_n8n_is_exit_2_and_quotes_no_content(tmp_path, body):
    f = tmp_path / "wf.json"
    f.write_text(body, encoding="utf-8")
    r = run(tmp_path, "--n8n", str(f))
    assert_named_refusal(r, MARK, "{not json")
    assert "not valid JSON" in r.stderr


def test_a_deeply_nested_n8n_file_is_exit_2_not_a_recursion_error(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    assert_named_refusal(run(tmp_path, "--n8n", str(f)))


def test_an_oversized_n8n_file_is_exit_2(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text("[" + " " * (2 * 1024 * 1024) + "]", encoding="utf-8")
    r = run(tmp_path, "--n8n", str(f))
    assert_named_refusal(r)
    assert "1 MiB" in r.stderr


def test_an_oversized_text_input_is_exit_2(tmp_path):
    f = tmp_path / "keys.csv"
    f.write_text("x" * (MAX_SCAN_BYTES + 1), encoding="utf-8")
    assert_named_refusal(run(tmp_path, "--secrets-text", str(f)))


def test_an_n8n_file_of_exactly_1_mib_is_scanned(tmp_path):
    f = tmp_path / "wf.json"
    body = "[" + " " * (MAX_SCAN_BYTES - 2) + "]"
    assert len(body.encode()) == MAX_SCAN_BYTES
    f.write_text(body, encoding="utf-8")
    r = run(tmp_path, "--n8n", str(f))
    assert r.exit_code == 0, r.output


def test_a_good_n8n_file_still_works(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text("[]", encoding="utf-8")
    assert run(tmp_path, "--n8n", str(f)).exit_code == 0
