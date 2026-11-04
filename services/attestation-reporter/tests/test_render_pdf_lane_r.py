"""Mutant survivor in render_pdf (Lane R): the no-browser refusal."""

import subprocess
from pathlib import Path

from attestation_reporter import render


def test_no_browser_is_reported_not_attempted(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "find_browser", lambda: None)
    called = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.append(a))
    ok, detail = render.render_pdf(tmp_path / "r.html", tmp_path / "r.pdf")
    assert ok is False
    assert "no Edge/Chrome found" in detail
    assert called == []


def test_a_found_browser_is_driven_and_a_pdf_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "find_browser", lambda: "/opt/fake/chrome")
    pdf = tmp_path / "r.pdf"

    def fake_run(cmd, **kw):
        assert cmd[0] == "/opt/fake/chrome"
        Path(pdf).write_bytes(b"%PDF-1.4 stub")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, detail = render.render_pdf(tmp_path / "r.html", pdf)
    assert ok is True and detail == "rendered by chrome"


def test_an_empty_pdf_is_not_a_success(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "find_browser", lambda: "/opt/fake/chrome")
    pdf = tmp_path / "r.pdf"
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: pdf.write_bytes(b""))
    ok, detail = render.render_pdf(tmp_path / "r.html", pdf)
    assert ok is False and "no PDF" in detail


def test_find_browser_returns_a_which_hit_then_an_existing_path_then_none(tmp_path, monkeypatch):
    monkeypatch.setattr(render.shutil, "which", lambda c: "/usr/bin/found" if c == "chrome" else None)
    assert render.find_browser() == "/usr/bin/found"
    exe = tmp_path / "msedge.exe"
    exe.write_text("x")
    monkeypatch.setattr(render.shutil, "which", lambda c: None)
    monkeypatch.setattr(render, "_BROWSER_CANDIDATES", ("nope-a", str(exe)))
    assert render.find_browser() == str(exe)
    monkeypatch.setattr(render, "_BROWSER_CANDIDATES", ("nope-a", str(tmp_path / "absent")))
    assert render.find_browser() is None
