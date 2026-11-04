"""FALLBACK pins (tests only): filters.parse_instant and witness.require_https had no test naming them."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sealed_ledger.filters import InvalidTimeBound, parse_bound, parse_instant
from sealed_ledger.witness import require_https


# ---- parse_instant --------------------------------------------------------------------------------------------------

def test_a_naive_timestamp_is_taken_as_utc():
    got = parse_instant("2026-09-01T10:00:00")
    assert got == datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc) and got.utcoffset() == timedelta(0)


def test_an_offset_is_kept_and_compares_as_the_same_instant():
    got = parse_instant("2026-09-01T10:00:00+02:00")
    assert got.utcoffset() == timedelta(hours=2)
    assert got == datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)


def test_a_z_suffix_is_utc():
    assert parse_instant("2026-09-01T10:00:00Z") == datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def test_a_bare_date_is_the_start_of_that_utc_day():
    assert parse_instant("2026-09-01") == datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def test_fractional_seconds_are_kept():
    assert parse_instant("2026-09-01T10:00:00.250000").microsecond == 250000


@pytest.mark.parametrize("bad", ["", "yesterday", "2026-13-01", "2026-09-01T25:00:00", "not-a-date"])
def test_garbage_is_a_value_error(bad):
    with pytest.raises(ValueError):
        parse_instant(bad)


def test_a_non_string_is_a_type_error():
    with pytest.raises(TypeError):
        parse_instant(20260901)  # type: ignore[arg-type]


def test_parse_bound_wraps_parse_instant_and_none_is_open():
    assert parse_bound("since", None) is None
    assert parse_bound("since", "2026-09-01") == parse_instant("2026-09-01")
    with pytest.raises(InvalidTimeBound) as e:
        parse_bound("until", "yesterday")
    assert str(e.value).startswith("until is not an ISO 8601 timestamp")


# ---- require_https --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://est.example", "https://est.example"),
    ("https://est.example/", "https://est.example"),
    ("https://est.example//", "https://est.example"),
    ("https://est.example:8443/base/", "https://est.example:8443/base"),
])
def test_an_https_url_passes_with_trailing_slashes_stripped(url, expected):
    assert require_https(url) == expected


@pytest.mark.parametrize("url", ["http://est.example", "ftp://est.example", "file:///etc/passwd", "est.example",
                                 "https://", "https:///path", "//est.example", "", "HTTP://est.example"])
def test_anything_but_https_with_a_host_is_refused(url):
    with pytest.raises(ValueError, match="must be an https:// URL"):
        require_https(url)
