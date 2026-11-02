"""C-1144 (reviewer Q-59 F-Q59-5 on PR 371): the one-line pins the reviewer's survivors asked for.

C12 a manifest behind an in-directory symlink resolves; C13 an unreadable file is ``invalid``, not ``missing``;
C15/C16 the cap is literally one mebibyte; A09 a manifest directory that is itself a symlink serves its files.
Every path here is a temp file and every manifest is the repository's own fixture."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import field_core.clients as fc

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "services" / "agent-registry" / "tests" / "fixtures" / "manifests" / "invoicing-agent.yaml"


@pytest.fixture()
def resolver(tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    shutil.copy(MANIFEST, d / "a.yaml")
    return fc.ManifestResolver(d), d


def test_the_cap_is_literally_one_mebibyte():
    """C15 and C16: the other tests import the constant, so a doubled or off-by-one cap went unnoticed."""
    assert fc.MAX_MANIFEST_BYTES == 1048576


@pytest.mark.skipif(not hasattr(Path, "symlink_to") or __import__("os").name == "nt",
                    reason="symlinks need privileges on Windows")
def test_a_manifest_behind_a_symlink_inside_the_directory_resolves(resolver):
    """C12: an lstat in place of the stat would refuse this file as invalid."""
    r, d = resolver
    (d / "link.yaml").symlink_to(d / "a.yaml")
    manifest, reason = r.resolve_detail("link.yaml")
    assert manifest is not None and reason == "ok"


@pytest.mark.skipif(__import__("os").name == "nt", reason="symlinks need privileges on Windows")
def test_a_manifest_directory_that_is_itself_a_symlink_serves_its_files(tmp_path):
    """A09: the base directory is followed, so a relative ref under it resolves."""
    real = tmp_path / "real"
    real.mkdir()
    shutil.copy(MANIFEST, real / "a.yaml")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    manifest, reason = fc.ManifestResolver(link).resolve_detail("a.yaml")
    assert manifest is not None and reason == "ok"


def test_an_unreadable_file_is_invalid_not_missing(resolver, monkeypatch):
    """C13: the file exists, so the answer is ``invalid``; a test run as root cannot chmod, so the open is made to fail."""
    r, d = resolver
    real_open = fc.os.open

    def deny(path, flags, *a, **k):
        if Path(path).name == "a.yaml":
            raise PermissionError(13, "denied")
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(fc.os, "open", deny)
    assert r.resolve_detail("a.yaml") == (None, "invalid")
