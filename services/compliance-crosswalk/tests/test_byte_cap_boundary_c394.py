"""C-394 (reviewer C-386 F-C386-1): the regwatch byte cap at its boundary, at every place it is enforced.

`MAX_BYTES` is checked on the declared `content-length`, on the streamed bytes, on an injected fetcher's bytes and on a
saved page (`check_file`, before and after reading). Each is `>` MAX_BYTES: a page of exactly MAX_BYTES is accepted, one
byte more is refused. The cap is lowered to a few hundred bytes so the tests stay small; the real value is pinned
separately."""

from __future__ import annotations

import httpx
import pytest

from compliance_crosswalk import regwatch
from compliance_crosswalk.mapping import SRC_OSFI
from compliance_crosswalk.staleness import StaleStore

CAP = 400
ANCHORS = ("Principle 1.1",)


@pytest.fixture(autouse=True)
def small_cap(monkeypatch):
    monkeypatch.setattr(regwatch, "MAX_BYTES", CAP)


def body(size: int) -> bytes:
    """An HTML page of exactly `size` bytes that names every identifier cited from the OSFI page (C-255)."""
    head, tail = b"<html><body><p>Principle 1.1 Principle 1.2 Principle 2.1 Principle 3.6 ", b"</p></body></html>"
    assert size >= len(head) + len(tail)
    return head + b"a" * (size - len(head) - len(tail)) + tail


def test_the_real_cap_is_eight_mebibytes(monkeypatch):
    monkeypatch.undo()
    assert regwatch.MAX_BYTES == 8 * 1024 * 1024


# --- an injected fetcher ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", [bytes, bytearray])
def test_an_injected_page_of_exactly_the_cap_is_accepted(kind):
    obs = regwatch._observe("osfi-e23", "official", SRC_OSFI, lambda url: kind(body(CAP)), ANCHORS)
    assert obs["ok"] is True and obs["raw_bytes"] == CAP


@pytest.mark.parametrize("kind", [bytes, bytearray])
def test_an_injected_page_one_byte_over_the_cap_is_refused(kind):
    obs = regwatch._observe("osfi-e23", "official", SRC_OSFI, lambda url: kind(body(CAP + 1)), ANCHORS)
    assert obs["ok"] is False and f"over the {CAP}-byte cap" in obs["error"]


def test_one_byte_under_the_cap_is_accepted():
    assert regwatch._observe("osfi-e23", "official", SRC_OSFI, lambda url: body(CAP - 1), ANCHORS)["ok"] is True


# --- the default fetcher (declared length and streamed bytes) -------------------------------------------------


def _mock(monkeypatch, handler):
    monkeypatch.setattr(regwatch, "_client_factory",
                        lambda: regwatch.build_http_client(httpx.MockTransport(handler)))


def test_a_streamed_page_of_exactly_the_cap_is_returned(monkeypatch):
    _mock(monkeypatch, lambda r: httpx.Response(200, content=body(CAP)))
    assert len(regwatch.default_fetcher(SRC_OSFI)) == CAP


def test_a_streamed_page_one_byte_over_the_cap_is_refused(monkeypatch):
    _mock(monkeypatch, lambda r: httpx.Response(200, content=body(CAP + 1)))
    with pytest.raises(regwatch.FetchError, match=f"over the {CAP}-byte cap"):
        regwatch.default_fetcher(SRC_OSFI)


def test_a_declared_length_of_exactly_the_cap_is_not_refused_up_front(monkeypatch):
    _mock(monkeypatch, lambda r: httpx.Response(200, content=body(CAP), headers={"content-length": str(CAP)}))
    assert len(regwatch.default_fetcher(SRC_OSFI)) == CAP


def test_a_declared_length_one_over_the_cap_is_refused_before_reading(monkeypatch):
    read = []

    class Counting(httpx.ByteStream):
        def __iter__(self):
            read.append(1)
            yield from super().__iter__()

    def handler(request):
        return httpx.Response(200, headers={"content-length": str(CAP + 1)}, stream=Counting(b"x" * (CAP + 1)))

    _mock(monkeypatch, handler)
    with pytest.raises(regwatch.FetchError, match=f"content-length {CAP + 1}"):
        regwatch.default_fetcher(SRC_OSFI)
    assert read == []


def test_a_non_numeric_declared_length_falls_through_to_the_streamed_count(monkeypatch):
    _mock(monkeypatch, lambda r: httpx.Response(200, content=body(CAP + 1), headers={"content-length": "abc"}))
    with pytest.raises(regwatch.FetchError, match=f"over the {CAP}-byte cap$"):
        regwatch.default_fetcher(SRC_OSFI)


# --- a saved page ---------------------------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    return StaleStore(tmp_path / "flags.json")


def test_a_saved_page_of_exactly_the_cap_is_accepted(store, tmp_path):
    f = tmp_path / "osfi-e23.html"
    f.write_bytes(b"<!doctype html>" + body(CAP - len(b"<!doctype html>")))
    assert f.stat().st_size == CAP
    report = regwatch.check_file("osfi-e23", f, "D. Hagell", store=store)
    assert report["exit_code"] == 0


def test_a_saved_page_one_byte_over_the_cap_is_refused_and_nothing_is_written(store, tmp_path):
    f = tmp_path / "osfi-e23.html"
    f.write_bytes(b"<!doctype html>" + body(CAP + 1 - len(b"<!doctype html>")))
    assert f.stat().st_size == CAP + 1
    with pytest.raises(regwatch.ManualFileRefused, match=f"over the {CAP}-byte cap"):
        regwatch.check_file("osfi-e23", f, "D. Hagell", store=store)
    assert store.source_record(SRC_OSFI) is None
