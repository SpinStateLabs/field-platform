"""S6-15: ``replay run`` with the service down, an HTML error page, or an unwritable ``--markdown`` path: one line and a
fixed exit code, never a traceback; the post-mortem is never lost (it goes to stdout when the file cannot be written)."""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from incident_replay import cli as cli_mod

runner = CliRunner()
ARGS = ["run", "invoicing-agent", "--since", "2026-01-01T00:00:00+00:00", "--until", "2026-01-02T00:00:00+00:00"]


class Resp:
    def __init__(self, status=200, text="{}"):
        self.status_code, self.text = status, text


class Stub:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.fixture()
def run(monkeypatch):
    monkeypatch.setenv("FIELD_REPLAY_URL", "http://127.0.0.1:8007")

    def go(outcome, *extra):
        stub = Stub(outcome)
        monkeypatch.setattr(cli_mod, "httpx", stub)
        r = runner.invoke(cli_mod.app, ARGS + list(extra))
        assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
        assert "Traceback" not in r.output
        return r, stub
    return go


ERRORS = [httpx.ConnectError("refused"), httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"),
          httpx.RemoteProtocolError("bad"), httpx.UnsupportedProtocol("x"), httpx.InvalidURL("bad")]


@pytest.mark.parametrize("exc", ERRORS, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("with_md", [False, True], ids=["json", "markdown"])
def test_an_unreachable_service_is_one_line_exit_1(run, tmp_path, exc, with_md):
    extra = ["--markdown", str(tmp_path / "pm.md")] if with_md else []
    r, _ = run(exc, *extra)
    assert r.exit_code == 1
    assert f"error: incident-replay unreachable ({type(exc).__name__})" in r.output and r.output.count("\n") == 1
    assert not (tmp_path / "pm.md").exists()


@pytest.mark.parametrize("with_md", [False, True], ids=["json", "markdown"])
def test_a_500_with_an_html_body_is_one_capped_line(run, tmp_path, with_md):
    html = "<html>" + "\n  <p>gateway exploded</p>" * 300 + "</html>"
    extra = ["--markdown", str(tmp_path / "pm.md")] if with_md else []
    r, _ = run(Resp(500, html), *extra)
    out = r.output.strip()
    assert r.exit_code == 1 and out.startswith("error 500:") and len(out.splitlines()) == 1 and len(out) < 260
    assert not (tmp_path / "pm.md").exists()                       # the file is written only after a 200


def test_json_mode_prints_the_post_mortem(run):
    r, stub = run(Resp(200, '{"agent_id": "invoicing-agent"}'))
    assert r.exit_code == 0 and '"agent_id"' in r.output
    assert stub.calls[0][0] == "http://127.0.0.1:8007/replay"


def test_markdown_mode_writes_the_file_after_a_200(run, tmp_path):
    p = tmp_path / "pm.md"
    r, stub = run(Resp(200, "# Post-mortem — invoicing-agent\n"), "--markdown", str(p))
    assert r.exit_code == 0 and f"post-mortem written to {p}" in r.output
    assert p.read_text(encoding="utf-8") == "# Post-mortem — invoicing-agent\n"
    assert stub.calls[0][0] == "http://127.0.0.1:8007/replay/markdown"


def test_markdown_into_a_missing_directory_is_exit_2_and_the_text_goes_to_stdout(run, tmp_path):
    r, _ = run(Resp(200, "# the post-mortem\n"), "--markdown", str(tmp_path / "nope" / "pm.md"))
    assert r.exit_code == 2
    assert "error: cannot write" in r.output and "FileNotFoundError" in r.output
    assert "# the post-mortem" in r.output                            # not lost


def test_markdown_at_a_directory_is_exit_2(run, tmp_path):
    r, _ = run(Resp(200, "# pm\n"), "--markdown", str(tmp_path))
    assert r.exit_code == 2 and "cannot write" in r.output and "# pm" in r.output


def test_a_nul_byte_in_the_path_is_exit_2_not_a_parse_error(run):
    r, _ = run(Resp(200, "# pm\n"), "--markdown", "a\x00b.md")
    assert r.exit_code == 2 and "cannot write" in r.output and "# pm" in r.output


def test_an_unwritable_file_is_exit_2(run, tmp_path):
    import os
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        if os.access(d, os.W_OK):
            pytest.skip("running as a user that ignores permissions")
        r, _ = run(Resp(200, "# pm\n"), "--markdown", str(d / "pm.md"))
        assert r.exit_code == 2 and "PermissionError" in r.output and "# pm" in r.output
    finally:
        d.chmod(0o700)
