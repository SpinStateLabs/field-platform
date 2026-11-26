"""S11-22: `sentinel score --out-json/--out-md` is tested, atomic, and never loses the printed result.

The files were written with a bare `write_text` after the whole live suite (about 100 checks, each ALLOW metered against
the governor) and BEFORE the summary lines, so an unwritable path was a traceback that threw the whole measurement
away. Now the gate summary is printed first; each file is written through a temporary file and `os.replace`; an
`OSError` is one class-only line and exit 1 (the measurement is on screen, the file is not on disk), and a failed
run leaves no half file and no temporary file behind.
"""
from __future__ import annotations

import json
import time

import httpx
import pytest
from typer.testing import CliRunner

from conformance_sentinel import cli as cli_mod

REAL_CLIENT = httpx.Client
SENTINEL, REGISTRY, DELEGATION = "http://sentinel.test", "http://registry.test", "http://delegation.test"


def _health(request):
    return httpx.Response(200, json={"mode": "log_only", "judge": "off"})


def _registry(request):
    return httpx.Response(201, json={})


def _delegation(request):
    if request.url.path.endswith("/revoke"):
        return httpx.Response(200, json={})
    return httpx.Response(201, json={"token_id": "tok-" + str(time.monotonic_ns())})


def _check(request):
    """Every seed answers ALLOW (a log-only sentinel with nothing it would have blocked): the run completes and the
    gates FAIL (exit 3); `gates_pass` below flips the verdict to PASS (exit 0) without faking a perfect corpus."""
    if request.url.path == "/health":
        return _health(request)
    return httpx.Response(200, json={"decision": "ALLOW", "context": {}})


@pytest.fixture()
def gates_pass(monkeypatch):
    from conformance_sentinel.measure import Scorecard
    monkeypatch.setattr(Scorecard, "gates_passed", property(lambda self: True))


@pytest.fixture()
def run(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_SENTINEL_URL", SENTINEL)
    monkeypatch.setenv("FIELD_REGISTRY_URL", REGISTRY)
    monkeypatch.setenv("FIELD_DELEGATION_URL", DELEGATION)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def invoke(*extra, sentinel=_check):
        handlers = {SENTINEL: sentinel, REGISTRY: _registry, DELEGATION: _delegation}
        monkeypatch.setattr(cli_mod.httpx, "Client", lambda base_url=None, **kw: REAL_CLIENT(
            base_url=base_url, transport=httpx.MockTransport(handlers[base_url])))
        return CliRunner().invoke(cli_mod.app, ["score", "--manifest-dir", str(tmp_path), *extra])

    return invoke


def test_a_good_run_writes_both_files_and_they_parse(run, gates_pass, tmp_path):
    js, md = tmp_path / "card.json", tmp_path / "card.md"
    res = run("--out-json", str(js), "--out-md", str(md))
    assert res.exit_code == 0, res.output
    card = json.loads(js.read_text(encoding="utf-8"))
    assert card["gates_passed"] is True and card["scorecard"]["total_seeds"] == 100 and "generated_at" in card["meta"]
    assert md.read_text(encoding="utf-8").startswith("#")
    assert "gates: PASS" in res.output


def test_the_gate_exit_code_3_survives_a_successful_write(run, tmp_path):
    js = tmp_path / "card.json"
    res = run("--out-json", str(js))
    assert res.exit_code == 3, res.output
    assert js.is_file() and "gates: FAIL" in res.output


def test_a_run_without_output_options_writes_nothing_and_keeps_its_exit_code(run, tmp_path):
    assert run().exit_code == 3
    assert not list(tmp_path.glob("*.json")) and not list(tmp_path.glob("*.md"))


@pytest.mark.parametrize("flag", ["--out-json", "--out-md"])
def test_an_unwritable_path_is_one_class_only_line_and_exit_1_after_the_summary(run, gates_pass, tmp_path, flag):
    blocker = tmp_path / "a-regular-file"
    blocker.write_text("x", encoding="utf-8")
    bad = blocker / "child" / "card.out"                 # a parent that is a regular file
    res = run(flag, str(bad))
    assert res.exit_code == 1, res.output
    assert isinstance(res.exception, SystemExit) and "Traceback" not in res.output
    assert "gates: PASS" in res.output                   # the measurement is not lost
    lines = [ln for ln in res.output.splitlines() if "not written" in ln]
    assert len(lines) == 1 and ("NotADirectoryError" in lines[0] or "FileNotFoundError" in lines[0])
    assert "a-regular-file" not in res.output and "child" not in res.output   # no path in the message
    assert res.output.index("gates: PASS") < res.output.index(lines[0])


def test_the_summary_is_printed_before_any_file_is_written(run, gates_pass, tmp_path, monkeypatch):
    events = []
    real_echo, real_write = cli_mod.typer.echo, cli_mod._write_atomic
    monkeypatch.setattr(cli_mod.typer, "echo", lambda m="", *a, **k: (events.append(("echo", str(m))), real_echo(m, *a, **k))[1])
    monkeypatch.setattr(cli_mod, "_write_atomic", lambda path, text: (events.append(("write", path)), real_write(path, text))[1])
    res = run("--out-json", str(tmp_path / "c.json"), "--out-md", str(tmp_path / "c.md"))
    assert res.exit_code == 0
    kinds = [k for k, _ in events]
    gate_line = next(i for i, (k, m) in enumerate(events) if k == "echo" and m.startswith("gates:"))
    writes = [i for i, k in enumerate(kinds) if k == "write"]
    assert len(writes) == 2 and min(writes) > gate_line


def test_a_failed_second_file_keeps_the_first_whole_and_leaves_no_temp_file(run, gates_pass, tmp_path):
    js = tmp_path / "card.json"
    blocker = tmp_path / "f"
    blocker.write_text("x", encoding="utf-8")
    res = run("--out-json", str(js), "--out-md", str(blocker / "card.md"))
    assert res.exit_code == 1
    json.loads(js.read_text(encoding="utf-8"))           # the first file is complete
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_a_failed_write_leaves_the_existing_file_untouched_and_no_temp(run, gates_pass, tmp_path, monkeypatch):
    js = tmp_path / "card.json"
    js.write_text("previous run", encoding="utf-8")

    def boom(src, dst):
        raise PermissionError("replace refused")
    monkeypatch.setattr(cli_mod.os, "replace", boom)
    res = run("--out-json", str(js))
    assert res.exit_code == 1 and "PermissionError" in res.output
    assert js.read_text(encoding="utf-8") == "previous run"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_a_failed_write_inside_the_temp_file_removes_it(run, gates_pass, tmp_path, monkeypatch):
    js = tmp_path / "card.json"
    real_open = open

    class Bad:
        def __init__(self, fh):
            self.fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return self.fh.__exit__(*a)

        def write(self, _):
            raise OSError("disk full")
    monkeypatch.setattr("builtins.open", lambda p, *a, **k: Bad(real_open(p, *a, **k))
                        if str(p).endswith(".tmp") else real_open(p, *a, **k))
    res = run("--out-json", str(js))
    assert res.exit_code == 1 and "OSError" in res.output
    assert not js.exists() and not list(tmp_path.glob("*.tmp"))
