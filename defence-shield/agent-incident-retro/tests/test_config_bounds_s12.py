"""S12-31: RetroConfig refuses values that silently disable a detection or authorize nearly every client.

clauses.py compares with `>` and `>=`, both False for NaN: a NaN `session_gap_s` never splits a session, a NaN
`pivot_window_s` never closes the window, a NaN `cadence_cv_max` makes S.cadence fire on every session with enough
requests; json.loads accepts NaN. Zero and negatives are as meaningless. And `if sub and sub.lower() in ua` accepted
`allow_ua_substrings: [" "]` (a space sits inside nearly every browser UA) so a one-character entry AUTHORIZED the lot.
The messages never echo the offending value."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from agent_incident_retro.cli import app
from agent_incident_retro.models import MIN_ALLOW_UA_CHARS, RetroConfig

SECRET = 7.123456789  # a value that must never be echoed back

FLOATS = ["session_gap_s", "pivot_window_s", "cadence_cv_max"]
BAD_FLOATS = [float("nan"), float("inf"), float("-inf"), 0.0, -1.0, -1e-9]


@pytest.mark.parametrize("field", FLOATS)
@pytest.mark.parametrize("value", BAD_FLOATS, ids=repr)
def test_a_non_finite_zero_or_negative_timing_is_refused(field, value):
    with pytest.raises(ValidationError) as exc:
        RetroConfig(**{field: value})
    assert f"{field} must be a finite number greater than 0" in str(exc.value)


@pytest.mark.parametrize("field", FLOATS)
def test_the_refusal_never_echoes_the_value(field):
    with pytest.raises(ValidationError) as exc:
        RetroConfig(**{field: -SECRET})
    msg = " ".join(e["msg"] for e in exc.value.errors())
    assert str(SECRET) not in msg and "7.1234" not in msg


@pytest.mark.parametrize("field", FLOATS)
@pytest.mark.parametrize("value", [1e-9, 0.01, 1.0, 1800.0, 1e12])
def test_a_finite_positive_timing_is_accepted(field, value):
    assert getattr(RetroConfig(**{field: value}), field) == value


@pytest.mark.parametrize("value", [0, -1, -100])
def test_cadence_min_requests_below_one_is_refused(value):
    with pytest.raises(ValidationError) as exc:
        RetroConfig(cadence_min_requests=value)
    assert "cadence_min_requests must be at least 1" in str(exc.value)


@pytest.mark.parametrize("value", [1, 2, 20, 10_000])
def test_cadence_min_requests_of_one_or_more_is_accepted(value):
    assert RetroConfig(cadence_min_requests=value).cadence_min_requests == value


def test_the_defaults_are_unchanged_and_valid():
    cfg = RetroConfig()
    assert (cfg.session_gap_s, cfg.pivot_window_s, cfg.cadence_min_requests, cfg.cadence_cv_max) == (1800.0, 300.0, 20, 0.35)
    assert math.isfinite(cfg.session_gap_s)


# ---- allow_ua_substrings -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("entry", [" ", "   ", "\t", "a", "ab", "abc", "a b", " abc ", "mo", "  ab  "], ids=repr)
def test_a_blank_or_too_short_ua_substring_is_refused(entry):
    with pytest.raises(ValidationError) as exc:
        RetroConfig(allow_ua_substrings=[entry])
    msg = " ".join(e["msg"] for e in exc.value.errors())
    assert f"allow_ua_substrings entries must be at least {MIN_ALLOW_UA_CHARS} characters" in msg
    assert repr(entry) not in msg


@pytest.mark.parametrize("entry", ["curl", "mozilla", "ZILLA", "Googlebot/2.1", " curl ", "python-requests"])
def test_a_real_ua_substring_is_accepted(entry):
    assert RetroConfig(allow_ua_substrings=[entry]).allow_ua_substrings == [entry]


def test_the_empty_string_stays_accepted_because_it_matches_nothing():
    """test_detection_pins_c148.py pins it: clauses.py skips an empty substring, so it authorizes nothing."""
    assert RetroConfig(allow_ua_substrings=[""]).allow_ua_substrings == [""]


def test_one_bad_entry_among_good_ones_refuses_the_whole_list():
    with pytest.raises(ValidationError):
        RetroConfig(allow_ua_substrings=["curl", "a"])


def test_the_minimum_is_four_characters():
    assert MIN_ALLOW_UA_CHARS == 4


# ---- the CLI ----------------------------------------------------------------------------------------------------

LOG = '203.0.113.5 - - [01/Sep/2026:00:00:{s:02d} +0000] "GET /about HTTP/1.1" 200 5 "-" "Mozilla/5.0"\n'


def _scan(tmp_path: Path, *extra: str):
    log = tmp_path / "a.log"
    log.write_text(LOG.format(s=0) + LOG.format(s=5), encoding="utf-8")
    runner = CliRunner()
    runner.invoke(app, ["keygen", "--out", str(tmp_path / "k"), "--pub", str(tmp_path / "p")])
    res = runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "o"), "--key", str(tmp_path / "k"), *extra])
    return res, tmp_path / "o"


def _cfg(tmp_path: Path, text: str) -> str:
    p = tmp_path / "cfg.json"
    p.write_text(text, encoding="utf-8")
    return str(p)


@pytest.mark.parametrize("body,field", [
    ('{"session_gap_s": NaN}', "session_gap_s"),
    ('{"pivot_window_s": Infinity}', "pivot_window_s"),
    ('{"cadence_cv_max": -Infinity}', "cadence_cv_max"),
    ('{"session_gap_s": 0}', "session_gap_s"),
    ('{"pivot_window_s": -5}', "pivot_window_s"),
])
def test_scan_with_a_bad_config_is_one_error_line_exit_1_and_scans_nothing(tmp_path, body, field):
    res, out = _scan(tmp_path, "--config", _cfg(tmp_path, body))
    assert res.exit_code == 1, res.output
    lines = [ln for ln in res.output.splitlines() if ln.strip()]
    assert lines == [f"error: {field} must be a finite number greater than 0"]
    assert "Traceback" not in res.output and not out.exists()


def test_scan_with_a_zero_session_gap_option_is_refused(tmp_path):
    res, out = _scan(tmp_path, "--session-gap-s", "0")
    assert res.exit_code == 1
    assert [ln for ln in res.output.splitlines() if ln.strip()] == ["error: session_gap_s must be a finite number greater than 0"]
    assert not out.exists()


def test_scan_with_cadence_min_requests_zero_is_refused(tmp_path):
    res, out = _scan(tmp_path, "--config", _cfg(tmp_path, '{"cadence_min_requests": 0}'))
    assert res.exit_code == 1
    assert [ln for ln in res.output.splitlines() if ln.strip()] == ["error: cadence_min_requests must be at least 1"]


@pytest.mark.parametrize("entry", [" ", "a", "ab"])
def test_scan_with_a_catch_all_ua_substring_is_refused_and_scans_nothing(tmp_path, entry):
    res, out = _scan(tmp_path, "--allow-ua", entry)
    assert res.exit_code == 1, res.output
    lines = [ln for ln in res.output.splitlines() if ln.strip()]
    assert lines == [f"error: allow_ua_substrings entries must be at least {MIN_ALLOW_UA_CHARS} characters after trimming"]
    assert not out.exists()


def test_scan_with_a_good_config_still_runs(tmp_path):
    res, out = _scan(tmp_path, "--config", _cfg(tmp_path, json.dumps({"session_gap_s": 60, "allow_ua_substrings": ["curl"]})))
    assert res.exit_code == 0, res.output
    assert (out / "report.md").exists()
