"""S3-17: `$` also matches before a final newline, so `_KEY_NAME.match('k\n')` and `_MANIFEST_NAME.match('x.yaml\n')`
were truthy and the name went on to build a path. fullmatch refuses both before anything is written."""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import volume_admin  # noqa: E402


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = volume_admin.main(list(argv))
    return code, out.getvalue()


@pytest.mark.parametrize("name", ["good\n", "good\r\n", "\ngood"])
def test_keys_generate_refuses_a_name_with_a_newline_and_writes_nothing(tmp_path, name):
    keys = tmp_path / "keys"
    code, out = _run("keys", "generate", "--dir", str(keys), name)
    assert code == 2 and "must match" in out
    assert not keys.exists() or list(keys.iterdir()) == []


def test_keys_generate_still_accepts_a_plain_name(tmp_path):
    keys = tmp_path / "keys"
    assert _run("keys", "generate", "--dir", str(keys), "good")[0] == 0
    assert (keys / "good.pem").is_file()


def test_manifests_install_refuses_a_name_with_a_newline_and_writes_nothing(tmp_path):
    estate = tmp_path / "estate"
    estate.mkdir()
    volume = tmp_path / "field-manifests"
    volume.mkdir()
    assert _run("manifests", "seed", "--estate", str(estate), "--volume", str(volume))[0] == 0
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.yaml").write_text("x: 1\n", encoding="utf-8")
    before = sorted(p.name for p in volume.iterdir())
    code, out = _run("manifests", "install", "--src", str(src), "--volume", str(volume), "a.yaml\n")
    assert code == 2 and "not a plain manifest file name" in out
    assert sorted(p.name for p in volume.iterdir()) == before
