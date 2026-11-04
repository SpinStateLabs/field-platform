"""Scout S-2-21: `agent_registry/redaction.py` pinned directly (no HTTP, no discover). The module was reached only through
`scan_secrets_text`, whose tests import `KEY_PATTERNS`, `MAX_SCAN_BYTES` and `ScanInputError`; `redact`, `fingerprint`,
`check_size`, `find_secrets` and `redact_text` named in no test. Tests only. Every key below is made up."""
from __future__ import annotations

import hashlib
import re

import pytest

from agent_registry.redaction import (
    KEY_PATTERNS, MAX_SCAN_BYTES, ScanInputError, check_size, find_secrets, fingerprint, redact, redact_text)

ANT = "sk-ant-" + "Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4z"            # 7 + 32 = 39 chars
OAI = "sk-" + "A1b2C3d4E5f6G7h8I9j0"                            # 3 + 20
GH = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"            # 4 + 36
AWS = "AKIA" + "ABCDEFGH12345678"                               # 4 + 16
GOOGLE = "AIza" + "A" * 35


# ---- redact ----------------------------------------------------------------------------------------------------------

def test_a_long_value_shows_seven_characters_an_ellipsis_and_the_last_four():
    v = "0123456789abcdefghijklmnopqrstuvwxyz"
    assert redact(v) == "0123456…wxyz"


@pytest.mark.parametrize("n,shown", [(21, 5), (20, 5), (12, 3), (8, 2), (4, 1), (3, 0), (2, 0), (1, 0), (0, 0)])
def test_a_short_value_shows_a_quarter_of_its_length(n, shown):
    v = "".join(chr(ord("a") + i % 26) for i in range(n))
    assert redact(v) == v[:shown] + "…"


def test_the_switch_is_at_exactly_22_characters():
    v21, v22 = "a" * 20 + "Z", "a" * 21 + "Z"
    assert redact(v21) == "a" * 5 + "…"                            # 21 // 4
    assert redact(v22) == "a" * 7 + "…" + "a" * 3 + "Z"            # 7 + ellipsis + 4


def test_an_empty_value_is_just_the_ellipsis():
    assert redact("") == "…"


@pytest.mark.parametrize("n", list(range(0, 80)) + [200, 1000])
def test_never_more_than_half_the_value_is_shown(n):
    shown = len(redact("x" * n).replace("…", ""))
    assert shown <= n / 2


# ---- fingerprint -----------------------------------------------------------------------------------------------------

def test_the_fingerprint_is_sha256_colon_16_hex_of_the_utf8_bytes_and_stable():
    fp = fingerprint("some-secret")
    assert re.fullmatch(r"sha256:[0-9a-f]{16}", fp)
    assert fp == "sha256:" + hashlib.sha256(b"some-secret").hexdigest()[:16]
    assert fp == fingerprint("some-secret") != fingerprint("some-secreT")


def test_the_fingerprint_hashes_utf8_not_the_characters():
    assert fingerprint("é€") == "sha256:" + hashlib.sha256("é€".encode("utf-8")).hexdigest()[:16]


# ---- check_size ------------------------------------------------------------------------------------------------------

def test_exactly_the_limit_in_bytes_is_accepted_and_one_more_is_refused():
    check_size("a" * MAX_SCAN_BYTES, "input")
    with pytest.raises(ScanInputError):
        check_size("a" * (MAX_SCAN_BYTES + 1), "input")


def test_size_counts_utf8_bytes_not_characters():
    assert MAX_SCAN_BYTES % 2 == 0
    check_size("é" * (MAX_SCAN_BYTES // 2), "input")                         # 2 bytes each: exactly the limit
    with pytest.raises(ScanInputError):                                       # fewer characters than the limit, more bytes
        check_size("é" * (MAX_SCAN_BYTES // 2) + "a", "input")
    check_size("€" * (MAX_SCAN_BYTES // 3), "input")                         # 3 bytes each: 1 under the limit
    with pytest.raises(ScanInputError):
        check_size("€" * (MAX_SCAN_BYTES // 3 + 1), "input")


def test_the_refusal_names_the_label_and_the_size_and_never_the_value():
    marker = "VALUE-MARKER-" + ANT
    with pytest.raises(ScanInputError) as e:
        check_size(marker + "a" * MAX_SCAN_BYTES, "secrets_text")
    msg = str(e.value)
    assert "secrets_text" in msg and f"{len(marker) + MAX_SCAN_BYTES} bytes" in msg and str(MAX_SCAN_BYTES) in msg
    assert "VALUE-MARKER" not in msg and ANT not in msg


def test_the_scan_input_error_is_a_value_error_but_not_a_pydantic_one():
    from pydantic import ValidationError
    assert issubclass(ScanInputError, ValueError) and not issubclass(ScanInputError, ValidationError)


# ---- find_secrets ----------------------------------------------------------------------------------------------------

def test_hits_come_back_in_text_order_whatever_the_pattern_order():
    text = f"first {GH} then {ANT} then {AWS}"
    hits = find_secrets(text, include_very_broad=False)
    assert [h.pattern for h in hits] == ["github-token", "anthropic", "aws-access-key-id"]
    assert [h.start for h in hits] == sorted(h.start for h in hits)
    for h in hits:
        assert text[h.start:h.end] == h.value


def test_each_span_is_counted_once_an_anthropic_key_is_never_also_an_openai_style_key():
    hits = find_secrets(f"key {ANT}", include_very_broad=False)
    assert [h.pattern for h in hits] == ["anthropic"]


def test_a_plain_sk_key_is_the_broad_openai_style_pattern():
    hits = find_secrets(f"key {OAI}", include_very_broad=False)
    assert [(h.pattern, h.breadth) for h in hits] == [("openai-style-sk", "broad")]


def test_a_scan_refuses_to_start_inside_a_longer_identifier():
    for text in (f"prod{ANT}", f"x{AWS}", f"wf-{OAI}", f"task-{OAI}", f"a_{GH}"):
        assert find_secrets(text, include_very_broad=False) == [], text


def test_a_fixed_length_key_does_not_end_inside_a_longer_identifier():
    assert find_secrets(GOOGLE, include_very_broad=False)[0].pattern == "google-api-key"
    assert find_secrets(GOOGLE + "X", include_very_broad=False) == []         # 40 characters is not a 39-character key
    assert find_secrets(AWS + "Q", include_very_broad=False) == []


def test_unbounded_finds_what_a_bounded_scan_skips():
    for text, name in ((f"prod{ANT}", "anthropic"), (f"x{AWS}", "aws-access-key-id"), (AWS + "Q", "aws-access-key-id"),
                       (GOOGLE + "X", "google-api-key")):
        assert find_secrets(text, include_very_broad=False) == []
        assert [h.pattern for h in find_secrets(text, include_very_broad=False, bounded=False)] == [name], text


def test_a_broad_sk_key_glued_by_a_dash_is_found_unbounded_but_not_when_glued_to_a_letter():
    assert [h.pattern for h in find_secrets(f"wf-{OAI}", include_very_broad=False, bounded=False)] == ["openai-style-sk"]
    assert [h.pattern for h in find_secrets(f"wf_{OAI}", include_very_broad=False, bounded=False)] == ["openai-style-sk"]
    assert find_secrets(f"task{OAI}", include_very_broad=False, bounded=False) == []
    assert find_secrets(f"a1{OAI}", include_very_broad=False, bounded=False) == []


def test_the_very_broad_assignment_pattern_is_off_unless_asked_for():
    text = "config api_key = abcdefghijkl1234"
    assert find_secrets(text, include_very_broad=False) == []
    (hit,) = find_secrets(text, include_very_broad=True)
    assert (hit.pattern, hit.breadth, hit.value) == ("assignment", "very-broad", "abcdefghijkl1234")


def test_a_value_shorter_than_twelve_is_not_an_assignment_hit():
    assert find_secrets("secret = elevenchars", include_very_broad=True) == []      # 11 characters
    assert [h.value for h in find_secrets("secret = twelve_chars", include_very_broad=True)] == ["twelve_chars"]  # 12


def test_a_span_claimed_by_a_provider_pattern_is_not_reclaimed_by_the_assignment_pattern():
    hits = find_secrets(f"token={ANT}", include_very_broad=True)
    assert [h.pattern for h in hits] == ["anthropic"]


def test_no_secret_gives_no_hits_and_every_pattern_has_a_distinct_name():
    assert find_secrets("nothing here, just words and 12345", include_very_broad=True) == []
    names = [p.name for p in KEY_PATTERNS]
    assert len(names) == len(set(names))


# ---- redact_text -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("word", ["task-planner-service", "desk-booking-2026", "risk-scoring-model", "disk-usage-report",
                                  "ask-anything-about-invoices", "plain words only", "", "ünï ✓ text"])
def test_readable_words_that_end_in_sk_stay_readable_and_plain_text_is_byte_identical(word):
    assert redact_text(word) == word


def test_a_glued_wf_key_is_replaced_and_the_rest_of_the_text_is_untouched():
    out = redact_text(f"before wf-{OAI} after")
    assert OAI not in out
    assert out.startswith("before wf-[REDACTED openai-style-sk ") and out.endswith("] after")
    assert redact(OAI) in out and fingerprint(OAI) in out


def test_a_provider_key_glued_to_anything_is_redacted():
    out = redact_text(f"prod{ANT}")
    assert ANT not in out and out.startswith("prod[REDACTED anthropic ")


def test_redact_text_replaces_every_hit_and_keeps_the_separators():
    out = redact_text(f"a {ANT}\nb {AWS}\tc")
    assert out.count("[REDACTED") == 2 and ANT not in out and AWS not in out
    assert out.startswith("a [REDACTED anthropic ") and "\nb [REDACTED aws-access-key-id " in out and out.endswith("]\tc")


def test_redact_text_includes_the_assignment_pattern():
    out = redact_text("api_key = abcdefghijkl1234 and more")
    assert "abcdefghijkl1234" not in out and "[REDACTED assignment " in out and out.endswith(" and more")


def test_a_redacted_form_never_contains_the_whole_value():
    out = redact_text(f"x {GH} y")
    assert GH not in out and GH[:7] in out and GH[-4:] in out
