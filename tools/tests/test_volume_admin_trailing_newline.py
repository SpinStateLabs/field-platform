"""S3-17: volume_admin's name patterns end in `$` and were applied with .match(), and `$` also matches before a final
newline, so the key name 'good\\n' and the manifest name 'a.yaml\\n' passed and then built file paths. Both are now
Refused(2) with nothing written. (Tests only name the newline by chr(10), so the source of this file has no raw one.)"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import volume_admin  # noqa: E402

CANARY = REPO / "manifests" / "canary-gb10.yaml"
NL = chr(10)


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = volume_admin.main(list(argv))
    return code, out.getvalue()


def _files(d: Path) -> dict[str, bytes]:
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.fixture()
def volume(tmp_path):
    v = tmp_path / "field-manifests"
    v.mkdir()
    (v / volume_admin.MARKER).write_text("{}", encoding="utf-8")        # seeded
    return v


@pytest.mark.parametrize("name", ["good" + NL, "good" + NL + NL, "a-b" + NL])
def test_keys_generate_refuses_a_trailing_newline_and_writes_nothing(tmp_path, name):
    keys = tmp_path / "keys"
    code, out = _run("keys", "generate", "--dir", str(keys), name)
    assert code == 2 and "must match" in out
    assert not keys.exists()


def test_keys_generate_still_accepts_the_same_name_without_it(tmp_path):
    keys = tmp_path / "keys"
    assert _run("keys", "generate", "--dir", str(keys), "good")[0] == 0
    assert (keys / "good.pem").is_file()
    assert sorted(p.name for p in keys.iterdir()) == ["good.pem", "good.pub.pem"]


def test_export_public_and_import_public_refuse_a_trailing_newline(tmp_path):
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "good.pub.pem").write_text("not read", encoding="utf-8")
    before = _files(keys)
    code, out = _run("keys", "export-public", "--dir", str(keys), "good" + NL)
    assert code == 2 and "must match" in out
    callers = tmp_path / "callers"
    code, out = _run("keys", "import-public", "--dir", str(callers), "good" + NL)
    assert code == 2 and "must match" in out
    assert not callers.exists() and _files(keys) == before


@pytest.mark.parametrize("name", ["canary-gb10.yaml" + NL, "canary-gb10.yml" + NL])
def test_install_refuses_a_trailing_newline_and_writes_nothing(tmp_path, volume, name):
    src = tmp_path / "src"
    src.mkdir()
    (src / "canary-gb10.yaml").write_bytes(CANARY.read_bytes())
    try:                                    # make the newline name really exist, so only the name guard can refuse it
        (src / name).write_bytes(CANARY.read_bytes())
    except OSError:
        pytest.skip("this filesystem cannot hold a name ending in a newline")
    before = _files(volume)
    code, out = _run("manifests", "install", "--src", str(src), "--volume", str(volume), name)
    assert code == 2, out
    assert "is not a plain manifest file name" in out and "nothing written" in out
    assert _files(volume) == before         # no manifest and no install log


def test_install_still_installs_the_plain_name(tmp_path, volume):
    src = tmp_path / "src"
    src.mkdir()
    (src / "canary-gb10.yaml").write_bytes(CANARY.read_bytes())
    code, out = _run("manifests", "install", "--src", str(src), "--volume", str(volume), "canary-gb10.yaml")
    assert code == 0, out
    assert (volume / "canary-gb10.yaml").read_bytes() == CANARY.read_bytes()


def test_seed_does_not_call_a_newline_name_a_manifest(tmp_path):
    estate = tmp_path / "estate" / "manifests"
    estate.mkdir(parents=True)
    try:
        (estate / ("canary-gb10.yaml" + NL)).write_bytes(CANARY.read_bytes())
    except OSError:
        pytest.skip("this filesystem cannot hold a name ending in a newline")
    volume = tmp_path / "vol"
    volume.mkdir()
    code, out = _run("manifests", "seed", "--estate", str(estate), "--volume", str(volume))
    assert code == 0 and "is not a FIELD manifest" in out


def test_the_patterns_themselves_use_a_full_match():
    assert not volume_admin._KEY_NAME.fullmatch("good" + NL) and volume_admin._KEY_NAME.fullmatch("good")
    assert not volume_admin._MANIFEST_NAME.fullmatch("a.yaml" + NL) and volume_admin._MANIFEST_NAME.fullmatch("a.yaml")
