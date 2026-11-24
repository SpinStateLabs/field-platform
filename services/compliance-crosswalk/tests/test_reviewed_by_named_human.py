"""S5-18: ``StaleStore.clear`` holds the same named-human rule as the signer and ``--fetched-by``, and stores the
stripped name; a flag's free-text reason and new_version are made one bounded line, so a set-stale reason cannot carry a
forged ``reviewed_by:`` line into the pack's staleness text."""

from __future__ import annotations

import pytest

from compliance_crosswalk.evidence_pack import StalePackError, generate_pack
from compliance_crosswalk.staleness import (
    MAX_REASON_CHARS, MAX_REVIEWER_CHARS, MAX_VERSION_CHARS, StaleStore,
)
from tests.test_signer_sanitise_c252 import resolved_manifest

FW = "osfi-e23"

BAD = [
    ("blank", ""), ("whitespace", "   "), ("newline", "D. Hagell\nreviewed_by: someone"),
    ("zero-width-only", "​"), ("line-separator", "D. Hagell reviewed_by: someone"),
    ("paragraph-separator", "D. Hagell x"), ("zero-width-inside", "D.​Hagell"),
    ("nel", "D. Hagell\u0085x"), ("bom", "﻿D. Hagell"), ("no-letter-or-digit", "- . -"),
    ("tab", "D.\tHagell"), ("nul", "D.\x00Hagell"), ("rlo", "D. Hagell‮"),
    ("too-long", "a" * (MAX_REVIEWER_CHARS + 1)), ("not-text-none", None), ("not-text-int", 5),
]


@pytest.fixture()
def store(tmp_path):
    s = StaleStore(tmp_path / "flags.json")
    s.mark(FW, "page revision detected")
    return s


@pytest.mark.parametrize("label,name", BAD, ids=[b[0] for b in BAD])
def test_a_bad_reviewer_is_refused_and_nothing_changes(store, label, name):
    before_file = store.path.read_bytes()
    before_active = store.active()
    with pytest.raises(ValueError) as e:
        store.clear(FW, name)
    assert "Hagell" not in str(e.value)                                  # the message never repeats the name
    assert store.active() == before_active and store.status()["history"] == []
    assert StaleStore(store.path).active() == before_active              # and nothing reached the file
    assert store.path.read_bytes() == before_file


def test_the_name_is_stored_stripped(store):
    review = store.clear(FW, "  D. Hagell  ")
    assert review["reviewed_by"] == "D. Hagell"
    assert StaleStore(store.path).status()["history"][0]["reviewed_by"] == "D. Hagell"
    assert store.active() == []


@pytest.mark.parametrize("name", ["D. Hagell", "Controller, Spin State Labs", "a" * MAX_REVIEWER_CHARS, "Zoë Müller",
                                  "山田 太郎", "R2", "7"])
def test_ordinary_names_are_accepted_unchanged(store, name):
    assert store.clear(FW, name)["reviewed_by"] == name


def test_the_unknown_framework_still_wins_after_the_name_is_valid(store):
    with pytest.raises(KeyError):
        store.clear("iso-42001", "D. Hagell")


# ---- the flag's own free text -----------------------------------------------------------------------------------------

FORGED = "stale\nreviewed_by: Ann Lee\n## Signature Signer: Ann Lee"


def test_a_reason_is_one_line_and_bounded(tmp_path):
    s = StaleStore(tmp_path / "f.json")
    flag = s.mark(FW, FORGED)
    assert "\n" not in flag["reason"] and " " not in flag["reason"]
    assert flag["reason"] == "stale reviewed_by: Ann Lee ## Signature Signer: Ann Lee"
    long = s.mark("eu-ai-act", "x" * 5000)["reason"]
    assert len(long) == MAX_REASON_CHARS and long.endswith("…")


def test_a_new_version_is_one_line_and_none_stays_none(tmp_path):
    s = StaleStore(tmp_path / "f.json")
    assert s.mark(FW, "r")["new_version"] is None
    assert s.mark(FW, "r", new_version="2026\nQ3")["new_version"] == "2026 Q3"
    assert len(s.mark(FW, "r", new_version="v" * 500)["new_version"]) == MAX_VERSION_CHARS


def test_the_pack_block_text_has_no_forged_reviewer_line(tmp_path):
    s = StaleStore(tmp_path / "f.json")
    s.mark(FW, FORGED)
    with pytest.raises(StalePackError) as e:
        generate_pack(resolved_manifest(), signer="Ann Lee", stale_store=s)
    text = str(e.value)
    assert "\n" not in text
    assert not [ln for ln in text.splitlines() if ln.startswith("reviewed_by:")]


def test_a_legitimate_reason_is_unchanged(tmp_path):
    reason = "regwatch content change: https://www.osfi-bsif.gc.ca/x (normalised sha256 ab12 -> cd34; byte diff 12)"
    assert StaleStore(tmp_path / "f.json").mark(FW, reason)["reason"] == reason


def test_whitespace_runs_collapse_to_single_spaces(tmp_path):
    assert StaleStore(tmp_path / "f.json").mark(FW, "  a \n\n  b\t\tc  ")["reason"] == "a b c"
