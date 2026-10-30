"""C-240 (reviewer C-141 F-C141-5, D-20): `--allow-ip` cannot be a catch-all, and an allowlist cannot make `scan` go quiet.

`--allow-ip 0.0.0.0/0` marked every hostile client AUTHORIZED and `scan` exited 0, so a scheduled run alerting on the
exit code said nothing. Now: a network wider than /8 (IPv4) or /32 (IPv6) is refused when the config is built (clear
error, exit 1, nothing scanned); and when no session is ESCALATE but at least one was AUTHORIZED by an allowlist `scan`
exits 3 (ESCALATE stays 2, a clean log stays 0)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from agent_incident_retro.cli import EXIT_AUTHORIZED_ONLY, EXIT_ESCALATE, app
from agent_incident_retro.models import MIN_ALLOW_PREFIX_V4, MIN_ALLOW_PREFIX_V6, RetroConfig

SQLI = "q=%27%20OR%20%271%27%3D%271"
LOG = ('{ip} - - [01/Sep/2026:00:00:{s:02d} +0000] "GET {target} HTTP/1.1" 200 5 "-" "Mozilla/5.0"\n')


def hostile_log(tmp_path: Path, ip="203.0.113.5") -> Path:
    log = tmp_path / "hostile.log"
    log.write_text(LOG.format(ip=ip, s=0, target="/search?q=books") + LOG.format(ip=ip, s=30, target="/search?" + SQLI),
                   encoding="utf-8")
    return log


def clean_log(tmp_path: Path) -> Path:
    log = tmp_path / "clean.log"
    log.write_text(LOG.format(ip="198.51.100.9", s=0, target="/about") + LOG.format(ip="198.51.100.9", s=5, target="/contact"),
                   encoding="utf-8")
    return log


def scan(tmp_path, log, *extra):
    tmp_path.mkdir(exist_ok=True)
    runner = CliRunner()
    runner.invoke(app, ["keygen", "--out", str(tmp_path / "k"), "--pub", str(tmp_path / "p")])
    return runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "o"), "--key", str(tmp_path / "k"), *extra])


WIDE = ["0.0.0.0/0", "0.0.0.0/1", "128.0.0.0/1", "10.0.0.0/7", "0.0.0.0/7", "::/0", "::/1",
        "2001::/16", "2001:db8::/31", "::ffff:0.0.0.0/96", "::ffff:0.0.0.0/100", "  0.0.0.0/0  "]
FINE = ["10.0.0.0/8", "203.0.113.0/24", "203.0.113.5", "203.0.113.5/32", "2001:db8::/32", "2001:db8::1", "2001:db8::/48",
        "::1", "127.0.0.1", "::ffff:203.0.113.5", "::ffff:10.0.0.0/104", "172.16.0.0/12"]
NOT_NETWORKS = ["not-an-ip", "unknown", "203.0.113.5/33", "", "300.1.1.1", "2001:db8::/129"]


@pytest.mark.parametrize("entry", WIDE)
def test_a_catch_all_or_too_wide_network_is_refused_when_the_config_is_built(entry):
    with pytest.raises(ValidationError, match="allow_ips entry"):
        RetroConfig(allow_ips=[entry])


@pytest.mark.parametrize("entry", FINE)
def test_a_network_at_or_above_the_floor_and_single_addresses_are_accepted(entry):
    assert RetroConfig(allow_ips=[entry]).allow_ips == [entry]


@pytest.mark.parametrize("entry", NOT_NETWORKS)
def test_an_entry_that_is_not_a_network_keeps_its_old_behaviour_and_widens_nothing(entry):
    assert RetroConfig(allow_ips=[entry]).allow_ips == [entry]


def test_the_floors_are_slash_8_and_slash_32():
    assert (MIN_ALLOW_PREFIX_V4, MIN_ALLOW_PREFIX_V6) == (8, 32)
    assert RetroConfig(allow_ips=["10.0.0.0/8"]) and RetroConfig(allow_ips=["2001:db8::/32"])
    with pytest.raises(ValidationError):
        RetroConfig(allow_ips=["10.0.0.0/7"])
    with pytest.raises(ValidationError):
        RetroConfig(allow_ips=["2001:db8::/31"])


def test_one_bad_entry_among_good_ones_refuses_the_whole_list():
    with pytest.raises(ValidationError, match="0.0.0.0/0"):
        RetroConfig(allow_ips=["203.0.113.0/24", "0.0.0.0/0", "198.51.100.7"])


def test_the_refusal_names_the_entry_and_the_floor():
    with pytest.raises(ValidationError) as exc:
        RetroConfig(allow_ips=["10.0.0.0/7"])
    msg = str(exc.value)
    assert "'10.0.0.0/7'" in msg and "/8" in msg and "IPv4" in msg
    with pytest.raises(ValidationError) as exc:
        RetroConfig(allow_ips=["2001::/16"])
    assert "/32" in str(exc.value) and "IPv6" in str(exc.value)


def test_a_config_file_cannot_smuggle_a_catch_all_either(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"allow_ips": ["0.0.0.0/0"]}', encoding="utf-8")
    r = scan(tmp_path / "run", hostile_log(tmp_path), "--config", str(cfg))
    assert r.exit_code == 1 and "error: allow_ips entry '0.0.0.0/0' is refused" in r.output


# --- the command ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("entry", ["0.0.0.0/0", "::/0", "10.0.0.0/7"])
def test_scan_refuses_a_catch_all_allow_ip_with_one_error_line_and_scans_nothing(tmp_path, entry):
    run = tmp_path / "run"
    r = scan(run, hostile_log(tmp_path), "--allow-ip", entry)
    assert r.exit_code == 1, r.output
    lines = [ln for ln in r.output.splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("error: allow_ips entry")
    assert "Traceback" not in r.output and not (run / "o").exists()


def test_the_probe_is_no_longer_silent_a_catch_all_cannot_exit_zero(tmp_path):
    """The reviewer's probe: every hostile client allowlisted by 0.0.0.0/0 used to exit 0."""
    r = scan(tmp_path / "run", hostile_log(tmp_path), "--allow-ip", "0.0.0.0/0")
    assert r.exit_code not in (0, EXIT_ESCALATE)


def test_the_exit_codes_are_distinct():
    assert {0, 1, EXIT_ESCALATE, EXIT_AUTHORIZED_ONLY} == {0, 1, 2, 3}


def test_a_hostile_log_without_an_allowlist_still_exits_2(tmp_path):
    r = scan(tmp_path / "run", hostile_log(tmp_path))
    assert r.exit_code == EXIT_ESCALATE and "ESCALATE 1" in r.output


def test_a_narrow_allowlist_that_authorizes_a_hostile_session_exits_3_with_a_note(tmp_path):
    r = scan(tmp_path / "run", hostile_log(tmp_path), "--allow-ip", "203.0.113.0/24")
    assert r.exit_code == EXIT_AUTHORIZED_ONLY, r.output
    assert "AUTHORIZED 1" in r.output and "ESCALATE 0" in r.output
    assert "AUTHORIZED by an allowlist" in r.output and "exit 3" in r.output


def test_an_allow_ua_that_authorizes_also_exits_3(tmp_path):
    r = scan(tmp_path / "run", hostile_log(tmp_path), "--allow-ua", "mozilla")
    assert r.exit_code == EXIT_AUTHORIZED_ONLY and "AUTHORIZED 1" in r.output


def test_an_escalate_beside_an_authorized_session_is_still_exit_2(tmp_path):
    log = tmp_path / "two.log"
    log.write_text(LOG.format(ip="203.0.113.5", s=0, target="/search?q=books")
                   + LOG.format(ip="203.0.113.5", s=30, target="/search?" + SQLI)
                   + LOG.format(ip="192.0.2.77", s=0, target="/search?q=books")
                   + LOG.format(ip="192.0.2.77", s=30, target="/search?" + SQLI), encoding="utf-8")
    r = scan(tmp_path / "run", log, "--allow-ip", "203.0.113.0/24")
    assert r.exit_code == EXIT_ESCALATE and "AUTHORIZED 1" in r.output and "ESCALATE 1" in r.output


def test_a_clean_log_with_an_unused_allowlist_exits_0(tmp_path):
    r = scan(tmp_path / "run", clean_log(tmp_path), "--allow-ip", "203.0.113.0/24")
    assert r.exit_code == 0 and "AUTHORIZED 0" in r.output


def test_a_clean_log_exits_0(tmp_path):
    assert scan(tmp_path / "run", clean_log(tmp_path)).exit_code == 0


def test_a_near_miss_allowlist_still_exits_2(tmp_path):
    r = scan(tmp_path / "run", hostile_log(tmp_path), "--allow-ip", "198.51.100.0/24")
    assert r.exit_code == EXIT_ESCALATE


def test_the_readme_documents_the_exit_codes_and_the_floor():
    text = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    for phrase in ("exits 2 when any session is ESCALATE", "exits 3", "AUTHORIZED by an allowlist", "wider than /8",
                   "/32 for IPv6", "0.0.0.0/0"):
        assert phrase in flat, phrase
