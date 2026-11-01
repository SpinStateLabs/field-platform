"""C-1086 (reviewer C-883 F-C883-2 on PR 371): the manifest resolver never reads an unbounded or non-regular file.

C-635 made the resolver cache content-keyed (sha256 of the bytes read). That read was ``path.read_bytes()`` on
whatever the ref named: a character device such as /dev/zero never ends (MemoryError after the address space is
gone, and MemoryError was not caught), a FIFO blocks the process, and a multi-gigabyte regular file is read whole
before anyone asks whether it is a manifest. Now: the ref must be a REGULAR file of at most MAX_MANIFEST_BYTES, and
the read itself is bounded (at most the cap plus one byte, so a file that grows between the stat and the read is
still refused). Anything else is ``invalid`` (it exists but is not a manifest), with no read at all."""

from __future__ import annotations

import os
import shutil
import signal
import stat
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


@pytest.fixture()
def no_read(monkeypatch):
    """Fail the test if the resolver hashes or parses anything: the refusal must come before the read."""
    def boom(*a, **k):
        raise AssertionError("the resolver read the file")
    monkeypatch.setattr(fc.hashlib, "sha256", boom)
    monkeypatch.setattr(fc, "parse_manifest_text", boom)
    monkeypatch.setattr(Path, "open", boom)  # not even opened


def test_the_cap_is_a_fixed_positive_constant():
    assert isinstance(fc.MAX_MANIFEST_BYTES, int) and 64 * 1024 <= fc.MAX_MANIFEST_BYTES <= 16 * 1024 * 1024
    assert MANIFEST.stat().st_size < fc.MAX_MANIFEST_BYTES  # the real fixtures fit with room to spare


def test_a_directory_is_invalid_and_never_read(resolver, no_read):
    r, d = resolver
    (d / "sub").mkdir()
    assert r.resolve_detail("sub") == (None, "invalid")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_a_fifo_is_invalid_and_never_opened(resolver, no_read):
    """Opening a FIFO with no writer blocks for ever; the stat alone must refuse it. An alarm turns a hang into a
    failure so a regression cannot stall the suite."""
    r, d = resolver
    os.mkfifo(d / "pipe.yaml")
    assert stat.S_ISFIFO((d / "pipe.yaml").stat().st_mode)

    def hung(signum, frame):
        raise AssertionError("the resolver opened the FIFO and blocked")

    old = signal.signal(signal.SIGALRM, hung)
    signal.alarm(5)
    try:
        assert r.resolve_detail("pipe.yaml") == (None, "invalid")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


@pytest.mark.skipif(not Path("/dev/zero").exists(), reason="no /dev/zero")
def test_a_character_device_behind_a_symlink_is_invalid_and_never_read(resolver, no_read):
    """The C-883 probe: an absolute ref (or a symlink inside the directory) to /dev/zero was read until MemoryError."""
    r, d = resolver
    os.symlink("/dev/zero", d / "zero.yaml")
    assert r.resolve_detail("zero.yaml") == (None, "invalid")
    assert r.resolve_detail("/dev/zero") == (None, "invalid")


def test_a_file_over_the_cap_is_invalid_and_never_read(resolver, no_read):
    r, d = resolver
    big = d / "big.yaml"
    with open(big, "wb") as fh:  # the builtin: the fixture has disarmed Path.open
        fh.truncate(fc.MAX_MANIFEST_BYTES + 1)  # sparse: the size is what matters, not the disk
    assert r.resolve_detail("big.yaml") == (None, "invalid")


def test_a_file_at_the_cap_is_still_read_and_judged_on_its_content(resolver, monkeypatch):
    """The boundary: exactly MAX_MANIFEST_BYTES is allowed (so the cap mutant `>=` goes red); the content then
    decides, and this content is not a manifest."""
    r, d = resolver
    at_cap = d / "cap.yaml"
    with at_cap.open("wb") as fh:
        fh.truncate(fc.MAX_MANIFEST_BYTES)
    parsed = []
    real = fc.parse_manifest_text
    monkeypatch.setattr(fc, "parse_manifest_text", lambda text, source: parsed.append(source) or real(text, source))
    assert r.resolve_detail("cap.yaml") == (None, "invalid")
    assert parsed == [at_cap]


def test_the_read_itself_is_bounded_when_the_file_grows_after_the_stat(resolver, monkeypatch):
    """A file that passes the size check and then grows (or lies about its size) is still refused: the resolver
    reads at most MAX_MANIFEST_BYTES + 1 bytes and never hands more than the cap to the hash or the parser."""
    r, d = resolver
    path = d / "grow.yaml"
    path.write_bytes(b"agent: {}\n")
    real_stat = Path.stat

    def small_stat(self, *a, **k):
        st = real_stat(self, *a, **k)
        if self == path:  # lie: report a tiny regular file, then grow it before the read
            with open(path, "ab") as fh:  # the builtin: Path.open is spied below
                fh.truncate(fc.MAX_MANIFEST_BYTES + 4096)
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid, st.st_gid, 10,
                                   st.st_atime, st.st_mtime, st.st_ctime))
        return st

    monkeypatch.setattr(Path, "stat", small_stat)
    reads = []
    real_open = Path.open

    class _Spy:
        def __init__(self, fh):
            self.fh = fh

        def read(self, n=-1):
            reads.append(n)
            return self.fh.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return self.fh.__exit__(*a)

    monkeypatch.setattr(Path, "open", lambda self, *a, **k: _Spy(real_open(self, *a, **k)))
    parsed = []
    monkeypatch.setattr(fc, "parse_manifest_text", lambda text, source: parsed.append(source))
    assert r.resolve_detail("grow.yaml") == (None, "invalid")
    assert parsed == []
    assert reads == [fc.MAX_MANIFEST_BYTES + 1], reads  # one bounded read, never fh.read()


def test_a_regular_manifest_still_resolves_and_is_cached(resolver, monkeypatch):
    r, d = resolver
    m, why = r.resolve_detail("a.yaml")
    assert why == "ok" and m is not None
    monkeypatch.setattr(fc, "parse_manifest_text", lambda text, source: (_ for _ in ()).throw(AssertionError("reparsed")))
    assert r.resolve_detail("a.yaml")[1] == "ok"
