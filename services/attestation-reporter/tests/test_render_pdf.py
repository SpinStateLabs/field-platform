"""`find_browser` and `render_pdf`: pinned, and a stale PDF is never reported as freshly rendered (scout P-17).

Before: nothing removed an earlier `board-pack.pdf`, so a browser that exited 0 without writing left the previous run's
PDF in place and `render_pdf` reported "rendered by <browser>" over it, next to a freshly written board-pack.json and
HTML that the old PDF does not match. No real browser is launched: `shutil.which`, `Path.exists` and `subprocess.run`
are replaced in `attestation_reporter.render`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from attestation_reporter import render
from attestation_reporter.render import find_browser, render_pdf


@pytest.fixture()
def html(tmp_path):
    p = tmp_path / "board-pack.html"
    p.write_text("<html></html>", encoding="utf-8")
    return p


class Runner:
    """A fake subprocess.run: records the call and optionally writes the target PDF."""

    def __init__(self, write: bytes | None = b"%PDF-1.4 new", exc: Exception | None = None):
        self.write, self.exc, self.calls = write, exc, []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if self.exc is not None:
            raise self.exc
        target = next(a.split("=", 1)[1] for a in cmd if a.startswith("--print-to-pdf="))
        if self.write is not None:
            Path(target).write_bytes(self.write)
        return subprocess.CompletedProcess(cmd, 0)


def _browser(monkeypatch, name="/usr/bin/chrome"):
    monkeypatch.setattr(render, "find_browser", lambda: name)


# -- find_browser -------------------------------------------------------------------------------------------


def test_find_browser_returns_a_path_hit(monkeypatch):
    monkeypatch.setattr(render.shutil, "which", lambda c: "/usr/bin/chrome" if c == "chrome" else None)
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert find_browser() == "/usr/bin/chrome"


def test_find_browser_returns_an_absolute_candidate_that_exists(monkeypatch):
    monkeypatch.setattr(render.shutil, "which", lambda c: None)
    monkeypatch.setattr(Path, "exists", lambda self: str(self).endswith("chrome.exe"))
    found = find_browser()
    assert found is not None and found.endswith("chrome.exe")


def test_find_browser_returns_none_when_nothing_is_there(monkeypatch):
    monkeypatch.setattr(render.shutil, "which", lambda c: None)
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert find_browser() is None


# -- render_pdf ---------------------------------------------------------------------------------------------


def test_no_browser_is_a_false_with_the_html_only_text(monkeypatch, html, tmp_path):
    monkeypatch.setattr(render, "find_browser", lambda: None)
    run = Runner()
    monkeypatch.setattr(render.subprocess, "run", run)
    ok, detail = render_pdf(html, tmp_path / "out.pdf")
    assert (ok, detail) == (False, "no Edge/Chrome found — HTML only (see LIMITS)") and run.calls == []


def test_a_browser_that_writes_a_pdf_is_rendered_by_its_name(monkeypatch, html, tmp_path):
    _browser(monkeypatch)
    run = Runner()
    monkeypatch.setattr(render.subprocess, "run", run)
    pdf = tmp_path / "out.pdf"
    assert render_pdf(html, pdf) == (True, "rendered by chrome")
    assert pdf.read_bytes() == b"%PDF-1.4 new"
    cmd = run.calls[0][0]
    assert cmd[0] == "/usr/bin/chrome" and f"--print-to-pdf={pdf}" in cmd and html.as_uri() in cmd
    assert run.calls[0][1]["timeout"] == 120 and run.calls[0][1]["check"] is True


def test_a_zero_byte_pdf_is_not_rendered(monkeypatch, html, tmp_path):
    _browser(monkeypatch)
    monkeypatch.setattr(render.subprocess, "run", Runner(write=b""))
    ok, detail = render_pdf(html, tmp_path / "out.pdf")
    assert ok is False and detail == "browser exited cleanly but produced no PDF"


def test_a_stale_pdf_is_never_reported_as_rendered(monkeypatch, html, tmp_path):
    _browser(monkeypatch)
    pdf = tmp_path / "board-pack.pdf"
    pdf.write_bytes(b"%PDF-1.4 OLD RUN")                       # a previous render, non-empty
    monkeypatch.setattr(render.subprocess, "run", Runner(write=None))   # the browser exits 0 and writes nothing
    ok, detail = render_pdf(html, pdf)
    assert ok is False and detail == "browser exited cleanly but produced no PDF"
    assert not pdf.exists(), "the stale PDF must not be left beside the new pack"


def test_a_fresh_render_replaces_a_stale_pdf(monkeypatch, html, tmp_path):
    _browser(monkeypatch)
    pdf = tmp_path / "board-pack.pdf"
    pdf.write_bytes(b"%PDF-1.4 OLD RUN")
    monkeypatch.setattr(render.subprocess, "run", Runner())
    assert render_pdf(html, pdf) == (True, "rendered by chrome")
    assert pdf.read_bytes() == b"%PDF-1.4 new"


@pytest.mark.parametrize("exc", [
    subprocess.CalledProcessError(1, "chrome"),
    subprocess.TimeoutExpired("chrome", 120),
])
def test_a_failing_or_timed_out_browser_is_a_false_and_leaves_no_stale_pdf(monkeypatch, html, tmp_path, exc):
    _browser(monkeypatch)
    pdf = tmp_path / "board-pack.pdf"
    pdf.write_bytes(b"%PDF-1.4 OLD RUN")
    monkeypatch.setattr(render.subprocess, "run", Runner(exc=exc))
    ok, detail = render_pdf(html, pdf)
    assert ok is False and detail.startswith("headless print failed: ")
    assert not pdf.exists()
