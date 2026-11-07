"""S10-7: no field-agent fixture, example or demo hard-codes a delegation expiry date.

The delegation mint gate reads the manifest's `delegation.expiry` with the REAL clock (`parse_expiry`; a date-only value is 00:00 UTC of that
day), so a literal such as 2027-06-30 in the Stack fixture, example 04 or demo.sh is a time bomb: the day after it, every field-agent
integration test that mints a token, the example and the demo fail with a gate refusal while no code changed. They compute the date from
the clock now (`future_expiry()` in conftest, one expression in the example and the demo). This scans the three places as text and fails on
a literal `20xx-xx-xx` date assigned to an expiry key, so the bomb cannot come back."""

import datetime
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

#: an `expiry` key (subscript or dict key, single or double quotes) set to a literal 20xx-xx-xx date
LITERAL = re.compile(r"""["']expiry["']\s*\]?\s*[=:]\s*["']20\d\d-\d\d-\d\d""")


def scanned():
    files = [PACKAGE / "tests" / "conftest.py", PACKAGE / "demo.sh", *sorted((PACKAGE / "examples").glob("*.py"))]
    assert len(files) >= 3 and all(f.is_file() for f in files)
    return files


def test_no_scanned_file_assigns_a_literal_date_to_an_expiry_key():
    offenders = []
    for f in scanned():
        for number, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if LITERAL.search(line):
                offenders.append(f"{f.relative_to(PACKAGE).as_posix()}:{number}")
    assert offenders == [], f"hard-coded expiry (a time bomb): {offenders}"


def test_the_scan_pattern_catches_the_spellings_it_is_for():
    for line in ('data["delegation"]["expiry"] = "2027-06-30"', "data['delegation']['expiry'] = '2030-01-01'",
                 '"expiry": "2028-12-31",', 'expiry = "2027-06-30"'.replace("expiry =", '"expiry" =')):
        assert LITERAL.search(line), line
    for line in ('data["delegation"]["expiry"] = future_expiry()', '"expiry": expiry_text', "# 2027-06-30 is gone"):
        assert not LITERAL.search(line), line


def test_future_expiry_is_an_iso_date_a_year_ahead_by_default():
    import conftest

    today = datetime.date.today()
    assert conftest.future_expiry() == (today + datetime.timedelta(days=365)).isoformat()
    assert conftest.future_expiry(days=30) == (today + datetime.timedelta(days=30)).isoformat()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", conftest.future_expiry())
    assert datetime.date.fromisoformat(conftest.future_expiry()) > today


def test_the_example_and_the_demo_compute_the_date_from_the_clock():
    example = (PACKAGE / "examples" / "04_bootstrap_operator.py").read_text(encoding="utf-8")
    demo = (PACKAGE / "demo.sh").read_text(encoding="utf-8")
    for text in (example, demo):
        assert "datetime.date.today()" in text and "timedelta(days=365)" in text
