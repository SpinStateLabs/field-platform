"""estate_probe heavy-route guard (item 2): the whole-ledger and whole-pack routes are refused without a filter
against a non-loopback base unless --allow-heavy is passed. Offline: the HTTP layer is replaced by a function
that raises, so any request that is sent fails the test; no host is contacted."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import estate_probe as ep  # noqa: E402

REMOTE = "https://estate.example.invalid"


class Sent(BaseException):
    """Raised by the fake HTTP layer: a request reached the network layer (BaseException: Estate.call turns
    every Exception into a transport_error answer, which would hide it)."""


@pytest.fixture
def no_http(monkeypatch):
    sent: list[str] = []

    def boom(req, *a, **k):
        sent.append(req.full_url)
        raise Sent(req.full_url)

    monkeypatch.setattr(ep._OPENER, "open", boom)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.delenv(ep.TIMEOUT_ENV, raising=False)
    monkeypatch.delenv(ep.ALLOW_HEAVY_ENV, raising=False)
    ep.RESULTS.clear()
    return sent


def _main(argv):
    try:
        return ep.main(argv)
    except SystemExit as exc:
        return exc.code


UNFILTERED = [
    ["health"], ["health", "--only", "attest"], ["pin"], ["continuity", "--count", "1", "--hash", "a" * 16],
    ["collateral", "--since", "0"],
    ["catalogue", "--agent", "canary-gb10", "--token", "t", "--expect-endpoint", "called"],
]


@pytest.mark.parametrize("cmd", UNFILTERED, ids=lambda c: c[0] + ("-only" if "--only" in c else ""))
def test_heavy_unfiltered_remote_refused_before_any_request(no_http, capsys, cmd):
    code = _main(["--base", REMOTE, *cmd])
    err = capsys.readouterr().err
    assert code == 2
    assert no_http == []
    assert "--allow-heavy" in err and "refusing" in err


@pytest.mark.parametrize("path", ["/attest/pack", "/ledger/verify", "/ledger/events", "/ledger/events?",
                                  "/attest/pack?org=x", "/ledger/events?limit=", "/ledger/verify?since=2026-01-01",
                                  "/ledger/verify?limit=", "/ledger/verify?limit=5"])
def test_call_backstop_refuses_unfiltered_heavy_path(no_http, path):
    with pytest.raises(SystemExit) as exc:
        ep.Estate(REMOTE, None, guard_heavy=True).call("GET", path)
    assert exc.value.code == 2 and no_http == []


@pytest.mark.parametrize("path", ["/ledger/events?limit=1", "/ledger/events?agent_id=a", "/ledger/events?event_type=t",
                                  "/ledger/events?since=2026-01-01", "/attest/pack?since=2026-01-01",
                                  "/attest/pack?period=2026-Q1", "/registry/agents", "/ledger/health"])
def test_filtered_or_light_remote_is_allowed(no_http, path):
    with pytest.raises(Sent):  # the request WAS attempted (and our fake HTTP layer raised)
        ep.Estate(REMOTE, None, guard_heavy=True).call("GET", path)
    assert len(no_http) == 1


def test_allow_heavy_flag_lets_the_request_through(no_http):
    with pytest.raises(Sent):
        ep.Estate(REMOTE, None, guard_heavy=False).call("GET", "/ledger/verify")
    assert no_http == [REMOTE + "/ledger/verify"]


def test_allow_heavy_cli_flag_reaches_the_network_layer(no_http):
    with pytest.raises(Sent):
        _main(["--base", REMOTE, "--allow-heavy", "pin"])
    assert no_http and no_http[0].endswith("/ledger/health")


@pytest.mark.parametrize("base", ["http://127.0.0.1:9", "http://127.5.5.5:9", "http://localhost:9", "http://[::1]:9",
                                  "http://[::ffff:127.0.0.1]:9"])
def test_local_bases_unchanged(no_http, base):
    for path in ("/attest/pack", "/ledger/verify", "/ledger/events"):
        with pytest.raises(Sent):
            ep.Estate(base, None, guard_heavy=True).call("GET", path)
    assert len(no_http) == 3


@pytest.mark.parametrize("base", ["http://10.0.0.5:9", "http://192.168.1.2:9", "http://128.0.0.1:9",
                                  "https://localhost.example.invalid", "http://127.0.0.1.example.invalid",
                                  "http://[::ffff:10.0.0.1]:9"])
def test_non_loopback_bases_are_remote(no_http, base):
    with pytest.raises(SystemExit):
        ep.Estate(base, None, guard_heavy=True).call("GET", "/ledger/verify")
    assert no_http == []


@pytest.mark.parametrize("base", ["https://evillocalhost", "http://notlocalhost:9", "https://evil.localhost",
                                  "http://xlocalhost", "http://localhost.evil.invalid"])
def test_host_merely_ending_in_localhost_is_remote(no_http, base):
    assert ep.is_loopback_base(base) is False
    with pytest.raises(SystemExit):
        ep.Estate(base, None, guard_heavy=True).call("GET", "/ledger/verify")
    assert no_http == []


@pytest.mark.parametrize("base", ["", "http://", "http:///x", "https://:8080", "estate"])
def test_empty_host_is_remote(no_http, base):
    assert ep.is_loopback_base(base) is False
    with pytest.raises(SystemExit):
        ep.Estate(base, None, guard_heavy=True).call("GET", "/ledger/verify")
    assert no_http == []


@pytest.mark.parametrize("base", ["http://10.0.0.5:9", "http://192.168.1.2:9", "http://172.16.0.1:9",
                                  "http://[fd00::1]:9", "http://[::ffff:10.0.0.1]:9", "https://evillocalhost"])
@pytest.mark.parametrize("cmd", [["pin"], ["health"], ["collateral", "--since", "0"]], ids=lambda c: c[0])
def test_cli_private_or_lookalike_base_sends_zero_requests(no_http, capsys, base, cmd):
    """The preflight uses the loopback predicate, not the wider private-network one: a private LAN base must be
    refused before the FIRST (light) request, not by the backstop after it."""
    code = _main(["--base", base, *cmd])
    assert code == 2
    assert no_http == []
    assert "--allow-heavy" in capsys.readouterr().err


@pytest.mark.parametrize("cmd", ["registry", "canary", "revoke", "refused-kill"])
def test_light_subcommands_have_no_heavy_route(cmd):
    assert ep._heavy_routes(cmd, argparse.Namespace(only=None)) == []


def test_health_only_without_attest_has_no_heavy_route():
    assert ep._heavy_routes("health", argparse.Namespace(only="registry,ledger")) == []


def test_help_and_docstring_document_the_flag(capsys):
    with pytest.raises(SystemExit):
        ep.main(["--help"])
    assert "--allow-heavy" in capsys.readouterr().out
    assert "--allow-heavy" in ep.__doc__


# -- review B-1: only estate_probe's own CLI guards; other tools that build an Estate are unchanged ------------

def test_default_estate_does_not_guard(no_http):
    """tools/phase_g_check.py builds ep.Estate(base, secret) and calls ep._events/_ledger unfiltered."""
    with pytest.raises(Sent):
        ep._events(ep.Estate(REMOTE, None))
    assert no_http == [REMOTE + "/ledger/events"]


@pytest.mark.parametrize("path", ["/ledger/verify", "/attest/pack", "/ledger/events"])
def test_default_estate_sends_every_heavy_route(no_http, path):
    with pytest.raises(Sent):
        ep.Estate(REMOTE, None).call("GET", path)
    assert no_http == [REMOTE + path]


def test_d16_record_check_remote_base_sends(no_http, tmp_path):
    import secrets
    import d16_record_check as dc
    f = tmp_path / "secret"
    f.write_text(secrets.token_hex(16), encoding="utf-8")
    with pytest.raises(Sent):
        dc.main(["--base", REMOTE, "--secret-file", str(f), "--operator-id", "op-x"])
    assert no_http == [REMOTE + "/ledger/events"]


def test_cli_main_builds_a_guarding_estate(monkeypatch):
    seen = {}

    def fake(estate, args):
        seen["guard"] = estate.guard_heavy
        return 0

    monkeypatch.setitem(ep.HANDLERS, "registry", fake)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    assert ep.main(["--base", REMOTE, "registry"]) == 0 and seen["guard"] is True
    assert ep.main(["--base", REMOTE, "--allow-heavy", "registry"]) == 0 and seen["guard"] is False


# -- go-live: FIELD_PROBE_ALLOW_HEAVY=1 is the environment route for a pinned caller that cannot pass flags ---

def test_env_name_is_pinned():
    assert ep.ALLOW_HEAVY_ENV == "FIELD_PROBE_ALLOW_HEAVY"


@pytest.mark.parametrize("value", ["0", "", " 1", "1 ", "true", "TRUE", "yes", "on", "11", "2", "-1", "1\n"])
def test_env_value_other_than_exact_1_stays_refused(no_http, monkeypatch, capsys, value):
    monkeypatch.setenv(ep.ALLOW_HEAVY_ENV, value)
    assert ep.allow_heavy(False) is False
    assert _main(["--base", REMOTE, "pin"]) == 2
    assert no_http == [] and "--allow-heavy" in capsys.readouterr().err


def test_env_exact_1_lets_the_request_through(no_http, monkeypatch):
    monkeypatch.setenv(ep.ALLOW_HEAVY_ENV, "1")
    with pytest.raises(Sent):
        _main(["--base", REMOTE, "pin"])
    assert no_http and no_http[0].endswith("/ledger/health")


def test_env_route_reaches_the_estate_backstop(monkeypatch):
    seen = {}

    def fake(estate, args):
        seen["guard"] = estate.guard_heavy
        return 0

    monkeypatch.setitem(ep.HANDLERS, "registry", fake)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv(ep.ALLOW_HEAVY_ENV, "1")
    assert ep.main(["--base", REMOTE, "registry"]) == 0 and seen["guard"] is False
    monkeypatch.setenv(ep.ALLOW_HEAVY_ENV, "yes")
    assert ep.main(["--base", REMOTE, "registry"]) == 0 and seen["guard"] is True


def test_env_route_reaches_ledger_events_on_pin(no_http, monkeypatch):
    # the preflight passes AND the backstop is off: pin must get past /ledger/health to /ledger/events
    monkeypatch.setenv(ep.ALLOW_HEAVY_ENV, "1")
    est = ep.Estate(REMOTE, None, guard_heavy=not ep.allow_heavy(False))
    with pytest.raises(Sent):
        est.call("GET", "/ledger/events")
    assert no_http == [REMOTE + "/ledger/events"]


def test_flag_still_works_with_env_unset(no_http):
    assert ep.allow_heavy(True) is True and ep.allow_heavy(False) is False


def test_help_and_docstring_document_the_env_route(capsys):
    with pytest.raises(SystemExit):
        ep.main(["--help"])
    assert ep.ALLOW_HEAVY_ENV in capsys.readouterr().out
    assert ep.ALLOW_HEAVY_ENV in ep.__doc__


def test_refusal_hint_says_the_flag_goes_before_the_subcommand(no_http, capsys):
    assert _main(["--base", REMOTE, "pin"]) == 2
    assert "--allow-heavy (before the subcommand)" in capsys.readouterr().err
