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
    monkeypatch.setattr(fc.os, "read", boom)  # opened (the type is decided on the descriptor), never read


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
    with open(big, "wb") as fh:
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


def test_the_read_itself_is_bounded_when_the_file_grows_after_the_size_check(resolver, monkeypatch):
    """A file that passes the size check on its descriptor and then grows (or lies about its size) is still
    refused: the resolver never asks for more than MAX_MANIFEST_BYTES + 1 bytes in all and never hands more than
    the cap to the hash or the parser."""
    r, d = resolver
    path = d / "grow.yaml"
    path.write_bytes(b"agent: {}\n")
    real_fstat = os.fstat

    def small_fstat(fd):
        st = real_fstat(fd)
        if stat.S_ISREG(st.st_mode) and st.st_size == len(b"agent: {}\n"):  # our file: lie, then grow it
            with open(path, "ab") as fh:
                fh.truncate(fc.MAX_MANIFEST_BYTES + 4096)
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid, st.st_gid, 10,
                                   st.st_atime, st.st_mtime, st.st_ctime))
        return st

    monkeypatch.setattr(fc.os, "fstat", small_fstat)
    asked, got = [], []
    real_read = os.read

    def spy_read(fd, n):
        asked.append(n)
        chunk = real_read(fd, n)
        got.append(len(chunk))
        return chunk

    monkeypatch.setattr(fc.os, "read", spy_read)
    parsed = []
    monkeypatch.setattr(fc, "parse_manifest_text", lambda text, source: parsed.append(source))
    assert r.resolve_detail("grow.yaml") == (None, "invalid")
    assert parsed == []
    assert asked and max(asked) <= fc.MAX_MANIFEST_BYTES + 1 and sum(got) <= fc.MAX_MANIFEST_BYTES + 1, (asked, got)


def test_the_type_is_decided_on_the_descriptor_not_on_the_path(resolver, monkeypatch):
    """F-Q59-4: a stat on the path and an open of the path are two looks. If what the open returns is a FIFO
    (the file was swapped between the two), the resolver sees that on the descriptor and refuses without a read,
    and without blocking: the descriptor is opened non-blocking. Simulated: os.open is made to hand back a FIFO
    descriptor for a path that stats as a regular manifest."""
    r, d = resolver
    os.mkfifo(d / "swapped.fifo")
    fifo_fd = os.open(d / "swapped.fifo", os.O_RDONLY | os.O_NONBLOCK)
    real_open = os.open

    def swapped_open(p, flags, *a, **k):
        if Path(p) == d / "a.yaml":
            assert flags & os.O_NONBLOCK, "the open must be non-blocking"
            return os.dup(fifo_fd)
        return real_open(p, flags, *a, **k)

    monkeypatch.setattr(fc.os, "open", swapped_open)
    monkeypatch.setattr(fc.os, "read", lambda fd, n: (_ for _ in ()).throw(AssertionError("read a FIFO")))
    monkeypatch.setattr(fc, "parse_manifest_text", lambda *a: (_ for _ in ()).throw(AssertionError("parsed")))

    def hung(signum, frame):
        raise AssertionError("the resolver blocked")

    old = signal.signal(signal.SIGALRM, hung)
    signal.alarm(5)
    try:
        assert r.resolve_detail("a.yaml") == (None, "invalid")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
        os.close(fifo_fd)


def test_a_regular_manifest_still_resolves_and_is_cached(resolver, monkeypatch):
    r, d = resolver
    m, why = r.resolve_detail("a.yaml")
    assert why == "ok" and m is not None
    monkeypatch.setattr(fc, "parse_manifest_text", lambda text, source: (_ for _ in ()).throw(AssertionError("reparsed")))
    assert r.resolve_detail("a.yaml")[1] == "ok"


# ------------------------------------------------------ Q-59 F-Q59-5: the pin gaps the reviewer measured

def test_a_manifest_behind_a_symlink_inside_the_directory_resolves(resolver):
    """C12: the type check follows the link (fstat on the opened file), so a linked manifest is a manifest."""
    r, d = resolver
    os.symlink(d / "a.yaml", d / "link.yaml")
    m, why = r.resolve_detail("link.yaml")
    assert why == "ok" and m is not None


def test_a_file_that_cannot_be_opened_is_invalid_not_missing(resolver, monkeypatch):
    """C13: it is there, so it is not "missing"; it cannot be a manifest for us, so it is "invalid"."""
    r, d = resolver
    real_open = os.open
    monkeypatch.setattr(fc.os, "open", lambda p, *a, **k: (_ for _ in ()).throw(PermissionError(13, "denied"))
                        if Path(p) == d / "a.yaml" else real_open(p, *a, **k))
    assert r.resolve_detail("a.yaml") == (None, "invalid")


def test_the_cap_is_one_mebibyte_and_the_boundary_is_pinned_by_literals(resolver, monkeypatch):
    """C15, C16: the figure itself, not the constant, decides; 1,048,576 bytes is read, 1,048,577 is not."""
    r, d = resolver
    assert fc.MAX_MANIFEST_BYTES == 1048576
    at, over = d / "at.yaml", d / "over.yaml"
    with open(at, "wb") as fh:
        fh.truncate(1048576)
    with open(over, "wb") as fh:
        fh.truncate(1048577)
    parsed = []
    monkeypatch.setattr(fc, "parse_manifest_text", lambda text, source: parsed.append(source) or {})
    monkeypatch.setattr(fc, "validate_manifest_data", lambda data: type("R", (), {"ok": False})())
    assert r.resolve_detail("at.yaml") == (None, "invalid") and parsed == [at]
    assert r.resolve_detail("over.yaml") == (None, "invalid") and parsed == [at]
