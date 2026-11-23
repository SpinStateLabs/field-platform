"""B-S11-27: volume_admin refuses a marker of the wrong JSON shape and leaves no orphan private key."""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import volume_admin  # noqa: E402


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = volume_admin.main(list(argv))
    return code, out.getvalue()


@pytest.mark.parametrize("body", [b"[]", b"null", b"5", b'"x"', b'{"files": 3}'])
def test_seed_refuses_a_marker_that_is_json_but_not_the_expected_shape(tmp_path, body):
    estate = tmp_path / "estate"
    estate.mkdir()
    volume = tmp_path / "vol"
    volume.mkdir()
    (volume / volume_admin.MARKER).write_bytes(body)
    code, out = _run("manifests", "seed", "--estate", str(estate), "--volume", str(volume))
    assert code == 1, out
    assert "unreadable" in out and "already seeded" not in out and "Traceback" not in out


def test_a_failed_public_key_write_removes_the_private_key_and_a_rerun_succeeds(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    real_open = os.open

    def failing_open(path, *a, **kw):
        if str(path).endswith(".pub.pem"):
            raise OSError(28, "No space left on device")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(volume_admin.os, "open", failing_open)
    code, out = _run("keys", "generate", "--dir", str(keys), "k1")
    assert code == 1, out
    assert "OSError" in out and "Traceback" not in out and "No space" not in out
    assert not list(keys.glob("*.pem"))
    monkeypatch.setattr(volume_admin.os, "open", real_open)
    code, out = _run("keys", "generate", "--dir", str(keys), "k1")
    assert code == 0, out
    assert (keys / "k1.pem").exists() and (keys / "k1.pub.pem").exists()


def test_main_maps_an_unexpected_oserror_to_one_stderr_line_and_exit_1(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise PermissionError("read-only file system")

    monkeypatch.setattr(volume_admin, "generate_key", boom)
    code, out = _run("keys", "generate", "--dir", str(tmp_path / "k"), "k1")
    assert code == 1 and "PermissionError" in out and "read-only" not in out and "Traceback" not in out
