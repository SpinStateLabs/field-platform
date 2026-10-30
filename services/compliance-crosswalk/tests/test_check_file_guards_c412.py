"""C-412 (reviewer C-406 F-C406-1): the two size guards of a saved page, pinned separately.

`read_manual_file` refuses a page over `MAX_BYTES` twice: on the size `stat` reports, before reading (the message names
the size), and on the bytes actually read, which also catches a file that grew after `stat` (the message does not). For
a page of exactly cap + 1 bytes the two agree, so only a stat that reports less than the file holds, or a message that
names the size, tells them apart."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from compliance_crosswalk import regwatch
from compliance_crosswalk.staleness import StaleStore

CAP = 400


@pytest.fixture(autouse=True)
def small_cap(monkeypatch):
    monkeypatch.setattr(regwatch, "MAX_BYTES", CAP)


@pytest.fixture
def store(tmp_path):
    return StaleStore(tmp_path / "flags.json")


def page(size: int) -> bytes:
    head, tail = b"<!doctype html><html><body><p>Principle 1.1 Principle 1.2 Principle 2.1 Principle 3.6 ", b"</p></body></html>"
    return head + b"a" * (size - len(head) - len(tail)) + tail


def _lying_stat(monkeypatch, reported: int):
    """`Path.stat` reports `reported` bytes for every file: the file 'grew' after `stat`."""
    real = Path.stat

    def stat(self, *a, **kw):
        r = real(self, *a, **kw)
        return SimpleNamespace(st_size=reported, st_mode=r.st_mode)

    monkeypatch.setattr(Path, "stat", stat)


@pytest.mark.parametrize("extra", [1, 2, 50])
def test_a_page_over_the_cap_is_refused_before_reading_and_the_message_names_its_size(tmp_path, extra):
    f = tmp_path / "p.html"
    f.write_bytes(page(CAP + extra))
    with pytest.raises(regwatch.ManualFileRefused) as e:
        regwatch.read_manual_file(f)
    assert f"over the {CAP}-byte cap" in str(e.value) and f"is {CAP + extra} bytes" in str(e.value)


@pytest.mark.parametrize("extra", [1, 2, 50])
def test_a_page_that_grew_after_stat_is_refused_on_the_bytes_read(monkeypatch, tmp_path, extra):
    f = tmp_path / "p.html"
    f.write_bytes(page(CAP + extra))
    _lying_stat(monkeypatch, 100)                            # stat says it fits; the read finds more
    with pytest.raises(regwatch.ManualFileRefused) as e:
        regwatch.read_manual_file(f)
    assert f"over the {CAP}-byte cap" in str(e.value) and " bytes" not in str(e.value)


def test_a_page_that_grew_after_stat_is_refused_by_check_file_and_nothing_is_written(monkeypatch, store, tmp_path):
    f = tmp_path / "osfi-e23.html"
    f.write_bytes(page(CAP + 1))
    _lying_stat(monkeypatch, 100)
    with pytest.raises(regwatch.ManualFileRefused, match=f"over the {CAP}-byte cap"):
        regwatch.check_file("osfi-e23", f, "D. Hagell", store=store)
    assert store.source_record(regwatch.inventory()["osfi-e23"].candidates[0][1]) is None


def test_a_page_of_exactly_the_cap_is_read_whole_even_when_stat_reports_it_correctly(tmp_path):
    f = tmp_path / "p.html"
    f.write_bytes(page(CAP))
    assert len(regwatch.read_manual_file(f)) == CAP and os.path.getsize(f) == CAP
