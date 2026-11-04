"""FALLBACK pins (tests only): signing.signer_public_pem and render.find_browser / render_pdf had no test naming them."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from attestation_reporter import render
from attestation_reporter.signing import InvalidSigningKey, signer_public_pem
from field_core.signing import generate_keypair


def pkcs8(key, password=None):
    enc = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc).decode("ascii")


# ---- signer_public_pem ----------------------------------------------------------------------------------------------

def test_the_public_pem_is_the_matching_spki_pem():
    private, public = generate_keypair()
    got = signer_public_pem(private)
    assert got == public or got.strip() == public.strip()
    assert got.startswith("-----BEGIN PUBLIC KEY-----\n") and got.endswith("-----END PUBLIC KEY-----\n")


def test_it_is_deterministic_and_matches_the_key_it_came_from():
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    assert signer_public_pem(pkcs8(key)) == pub == signer_public_pem(pkcs8(key))


@pytest.mark.parametrize("bad", [
    "", "not a pem", "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END PRIVATE KEY-----\n", "é",
    pkcs8(Ed25519PrivateKey.generate(), b"pw"),     # encrypted: password=None cannot load it
], ids=["empty", "text", "garbage-block", "non-ascii", "encrypted"])
def test_a_key_that_is_not_an_unencrypted_pem_private_key_is_refused_by_type_only(bad):
    with pytest.raises(InvalidSigningKey) as e:
        signer_public_pem(bad)
    assert "unencrypted PEM private key" in str(e.value)
    assert "QUJD" not in str(e.value)


def test_a_non_ed25519_private_key_is_refused():
    with pytest.raises(InvalidSigningKey) as e:
        signer_public_pem(pkcs8(X25519PrivateKey.generate()))
    assert str(e.value) == "signing key is not Ed25519"


@pytest.mark.parametrize("exc_type", ["UnsupportedAlgorithm", "TypeError", "ValueError"])
def test_each_loader_failure_is_a_named_refusal_not_an_escape(monkeypatch, exc_type):
    """UnsupportedAlgorithm is not a ValueError: a PKCS#8 key under an unknown algorithm OID must not escape."""
    from cryptography.exceptions import UnsupportedAlgorithm
    from attestation_reporter import signing

    exc = UnsupportedAlgorithm("x") if exc_type == "UnsupportedAlgorithm" else {"TypeError": TypeError, "ValueError": ValueError}[exc_type]("x")

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(signing.serialization, "load_pem_private_key", boom)
    with pytest.raises(InvalidSigningKey) as e:
        signer_public_pem("-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n")
    assert f"({exc_type})" in str(e.value)


def test_a_public_key_given_as_the_signing_key_is_refused():
    _, public = generate_keypair()
    with pytest.raises(InvalidSigningKey):
        signer_public_pem(public)


# ---- find_browser / render_pdf --------------------------------------------------------------------------------------

def test_find_browser_returns_the_first_candidate_that_resolves(monkeypatch):
    monkeypatch.setattr(render, "_BROWSER_CANDIDATES", ("one", "two", "three"))
    monkeypatch.setattr(render.shutil, "which", lambda c: f"/bin/{c}" if c in ("two", "three") else None)
    assert render.find_browser() == "/bin/two"


def test_find_browser_accepts_an_existing_path_candidate(monkeypatch, tmp_path):
    exe = tmp_path / "chrome"
    exe.write_text("x", encoding="utf-8")
    monkeypatch.setattr(render, "_BROWSER_CANDIDATES", ("absent", str(exe)))
    monkeypatch.setattr(render.shutil, "which", lambda c: None)
    assert render.find_browser() == str(exe)


def test_find_browser_is_none_when_nothing_resolves(monkeypatch):
    monkeypatch.setattr(render, "_BROWSER_CANDIDATES", ("nope-1", "/definitely/not/here"))
    monkeypatch.setattr(render.shutil, "which", lambda c: None)
    assert render.find_browser() is None


def test_render_pdf_without_a_browser_is_html_only(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "find_browser", lambda: None)
    ok, detail = render.render_pdf(tmp_path / "a.html", tmp_path / "a.pdf")
    assert ok is False and detail == "no Edge/Chrome found — HTML only (see LIMITS)"


def _fake_run(monkeypatch, write_bytes=None, exc=None, calls=None):
    def run(cmd, **kw):
        if calls is not None:
            calls.append((cmd, kw))
        if exc is not None:
            raise exc
        if write_bytes is not None:
            Path(next(a for a in cmd if a.startswith("--print-to-pdf=")).split("=", 1)[1]).write_bytes(write_bytes)
    monkeypatch.setattr(render, "find_browser", lambda: "/usr/bin/fake-chrome")
    monkeypatch.setattr(render.subprocess, "run", run)


def test_render_pdf_success_names_the_browser_and_passes_the_expected_arguments(monkeypatch, tmp_path):
    calls = []
    _fake_run(monkeypatch, write_bytes=b"%PDF-1.4", calls=calls)
    html = tmp_path / "a.html"
    html.write_text("<p>x</p>", encoding="utf-8")
    ok, detail = render.render_pdf(html, tmp_path / "a.pdf")
    assert (ok, detail) == (True, "rendered by fake-chrome")
    (cmd, kw), = calls
    assert cmd[0] == "/usr/bin/fake-chrome" and "--headless=new" in cmd and "--no-pdf-header-footer" in cmd and "--disable-gpu" in cmd and cmd[-1] == html.as_uri()
    assert f"--print-to-pdf={tmp_path / 'a.pdf'}" in cmd
    assert kw["check"] is True and kw["timeout"] == 120 and kw["capture_output"] is True


def test_render_pdf_clean_exit_with_no_file_is_not_success(monkeypatch, tmp_path):
    _fake_run(monkeypatch)
    ok, detail = render.render_pdf(tmp_path / "a.html", tmp_path / "a.pdf")
    assert (ok, detail) == (False, "browser exited cleanly but produced no PDF")


def test_render_pdf_an_empty_file_is_not_success(monkeypatch, tmp_path):
    _fake_run(monkeypatch, write_bytes=b"")
    ok, detail = render.render_pdf(tmp_path / "a.html", tmp_path / "a.pdf")
    assert ok is False and "no PDF" in detail


@pytest.mark.parametrize("exc", [subprocess.CalledProcessError(1, "x"), subprocess.TimeoutExpired("x", 120), OSError("boom")])
def test_render_pdf_a_browser_failure_is_a_best_effort_false(monkeypatch, tmp_path, exc):
    _fake_run(monkeypatch, exc=exc)
    ok, detail = render.render_pdf(tmp_path / "a.html", tmp_path / "a.pdf")
    assert ok is False and detail.startswith("headless print failed:")
