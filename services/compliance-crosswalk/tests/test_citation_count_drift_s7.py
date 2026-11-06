"""S7-34 — the 'N/M cited' count is stated in three places (the app description, README, SPEC). It is
computed here from CONTROLS x FRAMEWORKS, so adding or citing one entry without updating all three fails
this test and names the stale site. A compliance product that says 'never invented' cannot carry a stale
count. Tests only: the documents are matched by regex, not reworded."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from compliance_crosswalk.api import create_app
from compliance_crosswalk.engine import CoverageReport
from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ("cited", "pending-text", "pending-purchase")


def counts() -> tuple[int, int, Counter]:
    by_status: Counter = Counter()
    for c in CONTROLS:
        for fw in FRAMEWORKS:
            by_status[c.citations[fw].status] += 1
    total = sum(by_status.values())
    return by_status["cited"], total, by_status


def test_every_control_has_one_entry_per_framework():
    assert all(set(c.citations) == set(FRAMEWORKS) for c in CONTROLS)
    assert counts()[1] == len(CONTROLS) * len(FRAMEWORKS)


SITES = {
    "app description (api.py)": (lambda: create_app().description, r"(\d+)/(\d+)\s+cited"),
    "README.md": (lambda: (ROOT / "README.md").read_text(encoding="utf-8"),
                  r"\((\d+)/(\d+)\s+entries\s+cited\)"),
    "SPEC.md": (lambda: (ROOT / "SPEC.md").read_text(encoding="utf-8"),
                r"read\s+on\s+[\d-]+\s+\((\d+)/(\d+)\)"),
}


@pytest.mark.parametrize("site", SITES)
def test_the_stated_count_equals_the_computed_count(site):
    text_of, pattern = SITES[site]
    found = re.findall(pattern, text_of())
    assert found, f"{site}: no 'N/M cited' count found (the wording moved; update the regex, not the docs)"
    cited, total, _ = counts()
    for n, m in found:
        assert (int(n), int(m)) == (cited, total), (
            f"{site} says {n}/{m} cited but mapping.py computes {cited}/{total}")


def test_all_three_sites_agree_with_each_other():
    cited, total, _ = counts()
    stated = {s: re.findall(p, t()) for s, (t, p) in SITES.items()}
    assert all(v == [(str(cited), str(total))] * len(v) and v for v in stated.values()), stated


def test_a_stated_per_status_split_matches_the_computed_split():
    """Vacuous while the docs state no split; it bites the day a '23 pending-text' appears."""
    _, _, by_status = counts()
    docs = (ROOT / "README.md").read_text(encoding="utf-8") + (ROOT / "SPEC.md").read_text(encoding="utf-8")
    for status in STATUSES:
        for n in re.findall(rf"(\d+)\s+{re.escape(status)}\b", docs):
            assert int(n) == by_status[status], f"docs state {n} {status}, mapping.py computes {by_status[status]}"


def test_the_measured_split_is_pinned_so_a_change_is_a_visible_decision():
    cited, total, by_status = counts()
    assert (cited, total) == (16, 52)
    assert dict(by_status) == {"cited": 16, "pending-text": 23, "pending-purchase": 13}


def test_pending_purchase_is_only_ever_iso_and_iso_is_only_ever_pending_purchase():
    for c in CONTROLS:
        for fw in FRAMEWORKS:
            status = c.citations[fw].status
            if fw == "iso-42001":
                assert status == "pending-purchase", (c.control_id, status)
            else:
                assert status != "pending-purchase", (c.control_id, fw)


def test_the_citation_status_text_names_pending_purchase_only_for_iso():
    text = CoverageReport.model_fields["citation_status"].default
    sentences = [s for s in re.split(r"(?<=\.)\s+", text) if "pending-purchase" in s]
    assert sentences and all("ISO/IEC 42001" in s for s in sentences), sentences
    assert text.count("pending-purchase") == 1
