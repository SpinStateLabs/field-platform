"""S8-23 — the seeded scorecard manifest's delegation.expiry follows the clock, so the delegation mint
gate (which refuses every token once the manifest expiry is past, and a token expiring after it) cannot
turn `sentinel score` into a time bomb on a fixed date. The shipped self_manifest.yaml is a real
governance date and is NOT derived: it is pinned below as the next operator renewal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from conformance_sentinel import seeded
from conformance_sentinel.seeded import SEED_EXPIRY_DAYS, _seed_expiry, _seed_manifest_data
from field_core.validation import parse_expiry

LONGEST_TOKEN = timedelta(seconds=3600)      # the longest token the suite mints


def test_the_seed_expiry_is_ahead_of_now_by_a_year():
    exp = parse_expiry(_seed_manifest_data()["delegation"]["expiry"])
    now = datetime.now(timezone.utc)
    assert exp is not None
    assert exp > now + LONGEST_TOKEN + timedelta(days=300)
    assert exp <= now + timedelta(days=SEED_EXPIRY_DAYS + 2)


def test_the_expiry_is_derived_from_the_clock_not_a_literal():
    far = datetime(2040, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert _seed_expiry(far) == "2040-12-31"
    assert _seed_manifest_data(far)["delegation"]["expiry"] == "2040-12-31"
    # 2040 is a leap year: 365 days ahead is 12-31. The bomb the card names: on a clock past the old literal the seed is still valid
    after_the_old_date = datetime(2027, 7, 1, tzinfo=timezone.utc)
    assert parse_expiry(_seed_expiry(after_the_old_date)) > after_the_old_date + LONGEST_TOKEN


def test_the_expiry_is_a_date_only_iso_string():
    s = _seed_expiry(datetime(2026, 11, 5, 23, 59, tzinfo=timezone.utc))
    assert s == "2027-11-05" and len(s) == 10


def test_no_hard_coded_2027_literal_is_left_in_the_seed_module():
    assert "2027-06-30" not in Path(seeded.__file__).read_text(encoding="utf-8")


def test_the_conftest_manifest_uses_a_far_future_expiry():
    conftest = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
    assert "2027-06-30" not in conftest and "2099-12-31" in conftest


def test_the_shipped_self_manifest_expiry_is_the_named_governance_date():
    """A real date, renewed by the operator (not derived): when this test is edited the renewal happened."""
    path = Path(seeded.__file__).parent / "self_manifest.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert str(data["delegation"]["expiry"]) == "2027-06-30"
