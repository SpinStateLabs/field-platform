"""C-1154 (Don's ruling on reviewer C-1052 F-2 and F-3): a window refusal never repeats the caller's value, and the
week and basic ISO forms are refused with a named reason.

F-2: `/pack?period=<3000 characters>` came back as a 422 whose body held the whole value (window.py put `{text!r}` in
the message, api.py sent `str(exc)`). The refusals now name what is wrong in fixed text.
F-3: Python 3.11+ reads `2026W44` (a week) and `20261031` (a basic date) as dates, so `since=2026W44` was accepted as a
bound the ledger itself would not read. A bound must be the extended form: `YYYY-MM-DD`, optionally followed by a time.

Every value here is a made-up marker."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from attestation_reporter.api import create_app
from attestation_reporter.engine import PackEngine
from attestation_reporter.window import InvalidWindow, normalise_bound, parse_period
from field_core.authn import ENV_VAR

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def api(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    # no service clients: a bad window is refused before any service is queried
    return TestClient(create_app(engine=PackEngine()), raise_server_exceptions=False)


@pytest.mark.parametrize("params", [
    {"period": MARK * 100},                              # 3000 characters
    {"period": "Q9 " + MARK},                            # looks like a quarter, is not
    {"since": MARK, "until": "2026-10-31"},
    {"since": "2026-10-01", "until": MARK},
    {"since": "2026-10-01T" + MARK},
    {"since": MARK * 100},
])
@pytest.mark.parametrize("route", ["/pack", "/pack.html"])
def test_a_refused_window_does_not_repeat_the_value(api, route, params):
    r = api.get(route, params=params)
    assert r.status_code == 422, (route, params, r.status_code)
    assert MARK not in r.text, r.text
    assert len(r.text) < 400, len(r.text)        # a fixed reason, not the caller's text


def test_a_year_zero_period_is_refused_without_repeating_it(api):
    r = api.get("/pack", params={"period": "0000-Q1"})
    assert r.status_code == 422
    assert "0000-Q1" not in r.text


@pytest.mark.parametrize("bad", ["2026W44", "2026-W44-1", "2026W441", "20261031", "20261031T100000Z", "2026-304"])
def test_a_week_ordinal_or_basic_form_is_refused_by_name(bad):
    with pytest.raises(InvalidWindow) as info:
        normalise_bound("since", bad, end=False)
    assert "week" in str(info.value) and "YYYY-MM-DD" in str(info.value)
    assert bad not in str(info.value)


@pytest.mark.parametrize("bad", ["2026W44", "20261031"])
@pytest.mark.parametrize("name", ["since", "until"])
def test_the_api_refuses_a_week_or_basic_bound_with_a_named_422(api, name, bad):
    r = api.get("/pack", params={name: bad})
    assert r.status_code == 422, r.text
    assert "week" in r.text and "YYYY-MM-DD" in r.text
    assert bad not in r.text


@pytest.mark.parametrize("good", [
    "2026-10-31", "2026-10-31T10:00:00", "2026-10-31T10:00:00Z", "2026-10-31T10:00:00+02:00", "2026-10-31 10:00:00",
    " 2026-10-31 ",
])
def test_the_extended_forms_are_still_accepted(good):
    assert normalise_bound("since", good, end=False).year == 2026


@pytest.mark.parametrize("period", ["2026-Q3", "Q3 2026"])
def test_a_good_period_is_still_accepted(period):
    since, until = parse_period(period)
    assert since.year == until.year == 2026


@pytest.mark.parametrize("bound", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:00:00-05:00"])
def test_a_bound_with_no_utc_instant_is_refused_without_the_value(api, bound):
    with pytest.raises(InvalidWindow) as info:
        normalise_bound("since", bound, end=False)
    assert bound not in str(info.value)
    r = api.get("/pack", params={"since": bound})
    assert r.status_code == 422 and bound not in r.text


def test_the_refusal_messages_are_fixed_text():
    """The same refusal for any value: the message does not depend on what was sent."""
    seen = set()
    for value in ("a", MARK, MARK * 50):
        with pytest.raises(InvalidWindow) as info:
            parse_period(value)
        seen.add(str(info.value))
    assert len(seen) == 1
    seen = set()
    for value in ("yesterday", MARK, MARK * 50):
        with pytest.raises(InvalidWindow) as info:
            normalise_bound("since", value, end=False)
        seen.add(str(info.value))
    assert len(seen) == 1
