"""estate_probe is the evidence engine for every production deploy gate.

If it can report PASS on a broken estate, a broken deploy is declared green.
Every test here drives the REAL service code over real HTTP (estate_harness.py
mounts each service's create_app() under the prefixes Caddy routes) and asserts
BOTH directions: the check passes on a healthy estate, and fails on the exact
breakage it exists to catch. The fault tests are the nine false greens an
adversarial review (2026-09-12) reproduced against the first version; each one
fails if that hole reopens.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import harness_wait  # tools/tests is on sys.path (pytest rootdir/prepend import mode)

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import estate_probe  # noqa: E402

CANARY_MANIFEST = REPO / "manifests" / "canary-gb10.yaml"
HARNESS = Path(__file__).with_name("estate_harness.py")
SECRET = "estate-probe-test-secret-never-printed"
#: What both test estates' images were "built from" (every service reads it).
BUILD_SHA = "5d41402abc4b2a76b9719d911017c592ae1c0f3e"
CANARY = "canary-gb10"
RETIRED = "canary-gb10-retired"


# --- plumbing ---------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(method: str, url: str, body: dict | None = None, secret: str | None = None) -> tuple[int, object]:
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-field-auth"] = secret
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    return status, (json.loads(raw) if raw else None)


_COUNTER = [0]


def _uid(stem: str) -> str:
    """Per-test agent ids: tests share one estate, and the registry 409s a reuse."""
    _COUNTER[0] += 1
    return f"{stem}-{_COUNTER[0]}"


def _run(argv: list[str]) -> tuple[int, str]:
    """Call the probe in-process, capturing everything it prints."""
    estate_probe.RESULTS.clear()
    out = io.StringIO()
    saved = sys.stdout, sys.stderr
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = estate_probe.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    sys.stdout, sys.stderr = saved   # main() may have wrapped them in a redactor
    return code, out.getvalue()


@harness_wait.kills_proc_on_init_failure
class Estate:
    def __init__(self, tmp_path: Path, secret: bool):
        data = tmp_path / "data"
        (data / "manifests").mkdir(parents=True)
        self.manifest = data / "manifests" / "canary-gb10.yaml"
        self.manifest.write_bytes(CANARY_MANIFEST.read_bytes())
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.secret = SECRET if secret else None
        self.env = dict(os.environ)
        self.env.pop("FIELD_SHARED_SECRET", None)
        self.env["FIELD_BUILD_SHA"] = BUILD_SHA
        argv = [sys.executable, str(HARNESS), str(self.port), str(data)]
        if secret:
            argv.append("--secret")
            self.env["FIELD_SHARED_SECRET"] = SECRET
        wait = harness_wait.harness_wait(60)
        self.proc = subprocess.Popen(argv, env=self.env, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        deadline = time.time() + wait
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"harness exited early: {self.proc.returncode}")
            try:
                urllib.request.urlopen(f"{self.base}/ledger/health", timeout=2).read()
                break
            except OSError:
                time.sleep(0.3)
        else:
            raise RuntimeError("harness did not come up")
        self.token = self._provision()
        self._retire_a_canary()

    def _provision(self) -> str:
        """The canary is provisioned with the REAL lifecycle CLI, as a gate does."""
        env = dict(self.env)
        for prefix, var in (("registry", "FIELD_REGISTRY_URL"), ("ledger", "FIELD_LEDGER_URL"),
                            ("delegation", "FIELD_DELEGATION_URL"), ("governor", "FIELD_GOVERNOR_URL"),
                            ("killswitch", "FIELD_KILLSWITCH_URL")):
            env[var] = f"{self.base}/{prefix}"
        report = self.manifest.parent.parent / "canary.json"
        subprocess.run(
            [sys.executable, "-m", "lifecycle_manager.cli", "provision",
             "--manifest", str(self.manifest), "--owner", "FIELD canary", "--domain", "canary",
             "--grantor", "Don Hagell, Spin State Labs", "--ttl-days", "1",
             "--manifest-ref", str(self.manifest), "--out", str(report)],
            env=env, check=True, capture_output=True,
        )
        self._decommission_env = env
        return json.loads(report.read_text())["token_id"]

    def _retire_a_canary(self) -> None:
        """refused-kill's only legal target: a decommissioned canary."""
        status, _ = _http("POST", f"{self.base}/registry/agents",
                          {"agent_id": RETIRED, "name": "retired canary", "owner": "FIELD canary",
                           "domain": "canary"}, self.secret)
        assert status == 201
        subprocess.run([sys.executable, "-m", "lifecycle_manager.cli", "decommission", RETIRED,
                        "--by", "FIELD gate verification", "--reason", "refused-kill target"],
                       env=self._decommission_env, check=True, capture_output=True)

    CANARY_SCOPE = ["canary.probe", "canary.read", "canary.throttle", "canary.escalate", "llm.messages"]

    def reset(self) -> None:
        """Return the shared estate to a known state before each test: no faults,
        the canary back in its domain and alive, and a FRESH token (tests revoke
        theirs). Every step is verified, so a broken reset fails loudly instead of
        leaking one test's damage into the next."""
        self.fault()
        _http("PATCH", f"{self.base}/registry/agents/{CANARY}", {"domain": "canary"}, self.secret)
        # a fault test can flip the retired canary to killed; put it back so no
        # test depends on running after another
        status, rec = _http("GET", f"{self.base}/registry/agents/{RETIRED}", None, self.secret)
        if isinstance(rec, dict) and rec.get("status") != "retired":
            status, _ = _http("PATCH", f"{self.base}/registry/agents/{RETIRED}",
                              {"status": "retired"}, self.secret)
            assert status == 200
        status, hb = _http("GET", f"{self.base}/killswitch/heartbeat/{CANARY}", None, self.secret)
        if isinstance(hb, dict) and hb.get("killed"):
            status, _ = _http("POST", f"{self.base}/killswitch/revive/{CANARY}",
                              {"operator": "test reset", "reason": "reset"}, self.secret)
            assert status == 200
        status, tok = _http("POST", f"{self.base}/delegation/tokens",
                            {"agent_id": CANARY, "granted_by": "Don Hagell, Spin State Labs",
                             "scope": self.CANARY_SCOPE, "ttl_seconds": 86400}, self.secret)
        assert status in (200, 201), status
        self.token = tok["token_id"]

    def fault(self, *names: str) -> None:
        status, body = _http("POST", f"{self.base}/__fault", {"on": list(names)})
        assert status == 200 and sorted(body["on"]) == sorted(names)

    def argv(self, *rest: str) -> list[str]:
        return ["--base", self.base, *rest]

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=20)


@pytest.fixture(scope="module")
def _open_estate(tmp_path_factory):
    saved = os.environ.pop("FIELD_SHARED_SECRET", None)
    e = Estate(tmp_path_factory.mktemp("open"), secret=False)
    try:
        yield e
    finally:
        e.close()
        if saved is not None:
            os.environ["FIELD_SHARED_SECRET"] = saved


@pytest.fixture(scope="module")
def _secret_estate(tmp_path_factory):
    e = Estate(tmp_path_factory.mktemp("secret"), secret=True)
    try:
        yield e
    finally:
        e.close()


@pytest.fixture()
def estate(_open_estate, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    _open_estate.reset()
    return _open_estate


@pytest.fixture()
def secret_estate(_secret_estate, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    _secret_estate.reset()
    return _secret_estate


def _catalogue(e: Estate) -> tuple[int, str]:
    return _run(e.argv("catalogue", "--agent", CANARY, "--token", e.token,
                       "--expect-endpoint", "skipped"))


# --- a healthy estate is green ------------------------------------------------------


def test_every_subcommand_passes_on_a_healthy_estate(estate):
    e = estate
    assert _run(e.argv("health"))[0] == 0
    code, out = _run(e.argv("canary", "--agent", CANARY, "--token", e.token))
    assert code == 0, out
    code, out = _catalogue(e)
    assert code == 0, out
    code, out = _run(e.argv("refused-kill", "--agent", RETIRED))
    assert code == 0, out
    pin = json.loads(_run(e.argv("pin"))[1].strip().splitlines()[-1])
    assert _run(e.argv("continuity", "--count", str(pin["event_count"]),
                       "--hash", pin["head_hash_prefix"]))[0] == 0
    assert _run(e.argv("revoke", "--agent", CANARY, "--token", e.token))[0] == 0


def test_the_secret_estate_is_green_and_the_perimeter_is_verified(secret_estate):
    e = secret_estate
    code, out = _run(e.argv("health", "--expect-perimeter"))
    assert code == 0, out
    code, out = _catalogue(e)
    assert code == 0, out


# --- B1: a failed ledger read never counts as empty ------------------------------------


def test_b1_collateral_fails_when_the_ledger_cannot_be_read(estate):
    estate.fault("ledger_events_500")
    code, out = _run(estate.argv("collateral", "--since", "0"))
    assert code == 1
    assert "no events about" not in out


def test_b1_pin_fails_on_an_unreadable_ledger_instead_of_pinning_zero(estate):
    estate.fault("ledger_events_500_unfiltered")
    assert _run(estate.argv("pin"))[0] == 1


def test_b1_continuity_refuses_a_vacuous_pin(estate):
    assert _run(estate.argv("continuity", "--count", "0", "--hash", "0" * 16))[0] == 2
    assert _run(estate.argv("continuity", "--count", "1", "--hash", ""))[0] == 2


def test_b1_collateral_since_past_the_end_fails(estate):
    code, _ = _run(estate.argv("collateral", "--since", "100000"))
    assert code == 1


# --- B2: the three ledger routes must agree ---------------------------------------------


def test_b2_pin_fails_when_events_is_truncated_against_health_and_verify(estate):
    estate.fault("ledger_events_truncated")
    assert _run(estate.argv("pin"))[0] == 1


# --- B3: kill, revive and drill must be audited ------------------------------------------


def test_b3_catalogue_fails_when_the_killswitch_writes_no_ledger_events(estate):
    estate.fault("ks_ledger_dead")
    code, out = _catalogue(estate)
    assert code == 1
    assert "exactly +1 kill.agent" in out


def test_b3_a_drill_answered_500_fails_and_prints_restored_from_the_detail(estate):
    """C-19: a drill whose restore failed is a 500 with the report as the detail. The check
    still FAILs, and its message reads the report from the detail (restored=False, not None)."""
    estate.fault("drill_500_not_restored")
    code, out = _catalogue(estate)
    assert code == 1, out
    assert ("[FAIL] B3 drill restored=true restored_status=active (got HTTP 500 "
            "restored=False restored_status=<restore failed>)") in out, out


# --- B4: a drill must actually restore the canary ----------------------------------------


def test_b4_catalogue_fails_when_a_drill_leaves_the_canary_killed(estate):
    estate.fault("drill_leaves_killed")
    code, out = _catalogue(estate)
    assert code == 1, out
    # red for THIS reason (the canary is left killed), not because the drill itself errored
    assert "[FAIL] B3 heartbeat 200 killed=false after the drill" in out, out


def test_b4_drill_fault_rekills_before_the_drill_is_answered(estate):
    """CI run 40288779166 (tests 3.11): the test above once exited 0. The
    drill_leaves_killed fault answered the drill (restored=true) and only then
    PATCHed the canary back to killed, so a heartbeat read served before that
    PATCH landed saw 'active' and the probe passed. 'drill_rekill_after_heartbeat'
    holds the re-kill until a heartbeat has been served (bounded), forcing that
    interleaving every time: with the re-kill applied before the drill answer the
    caller cannot reach the heartbeat first, so the probe must still fail, and on
    the heartbeat-after-drill check."""
    estate.fault("drill_leaves_killed", "drill_rekill_after_heartbeat")
    code, out = _catalogue(estate)
    assert code == 1, out
    assert "[FAIL] B3 heartbeat 200 killed=false after the drill" in out, out


def test_b4_catalogue_fails_when_kill_or_revive_return_200_without_flipping(estate):
    estate.fault("kill_200_noflip")
    assert _catalogue(estate)[0] == 1


# --- B5: the secret never reaches any output ---------------------------------------------


def test_b5_a_secret_with_a_carriage_return_is_refused_not_printed(estate, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET + "\r")
    code, out = _run(estate.argv("health"))
    assert code == 2
    assert SECRET not in out


def test_b5_a_multiline_or_empty_secret_file_is_refused(estate, tmp_path):
    two_lines = tmp_path / "s2"
    two_lines.write_text(SECRET + "\nsecond line\n")
    empty = tmp_path / "s0"
    empty.write_text("")
    for f in (two_lines, empty, tmp_path / "missing"):
        code, out = _run(["--base", estate.base, "--secret-file", str(f), "health"])
        assert code == 2
        assert SECRET not in out


def test_b5_the_secret_never_appears_in_any_output(secret_estate):
    e = secret_estate
    outputs = [_run(e.argv(*a))[1] for a in (
        ("health", "--expect-perimeter"), ("pin",),
        ("canary", "--agent", CANARY, "--token", e.token),
        ("catalogue", "--agent", CANARY, "--token", e.token, "--expect-endpoint", "skipped"),
        ("revoke", "--agent", CANARY, "--token", e.token),
    )]
    outputs.append(_run(["--base", "http://127.0.0.1:1", "health"])[1])
    e.fault("introspect_echo_headers")
    outputs.append(_run(e.argv("revoke", "--agent", CANARY, "--token", e.token))[1])
    assert SECRET not in "\n".join(outputs)


def test_b5_cleartext_to_a_public_host_is_refused_with_a_secret(monkeypatch):
    """Refused before any connection is attempted. A hostname is used because
    Python's ipaddress classes the documentation ranges (203.0.113.0/24) as
    private, which would make this test pass for the wrong reason."""
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    for base in ("http://estate.example.com", "http://8.8.8.8"):
        code, out = _run(["--base", base, "health"])
        assert code == 2, base
        assert SECRET not in out
    # https to the same public host is allowed to proceed (and simply fails to
    # connect here) — the guard is about cleartext, not about public hosts.
    code, _ = _run(["--base", "https://127.0.0.1:1", "health"])
    assert code == 1


# --- B6/B7: rule 7 — only the exact canary, only its own token -----------------------------


def test_b6_revoke_refuses_a_token_that_belongs_to_another_agent(estate):
    e = estate
    real = _uid("real-agent")
    status, _ = _http("POST", f"{e.base}/registry/agents",
                      {"agent_id": real, "name": "r", "owner": "o", "domain": "finance"})
    assert status == 201
    status, tok = _http("POST", f"{e.base}/delegation/tokens",
                        {"agent_id": real, "granted_by": "Don Hagell",
                         "scope": ["x"], "ttl_seconds": 3600})
    assert status in (200, 201), status
    code, _ = _run(e.argv("revoke", "--agent", CANARY, "--token", tok["token_id"]))
    assert code == 2
    status, token_now = _http("GET", f"{e.base}/delegation/tokens/{tok['token_id']}")
    assert status == 200 and token_now["revoked"] is False


def test_b7_a_real_agent_named_canary_something_is_not_a_canary(estate):
    e = estate
    lookalike = _uid("canary-release-bot")
    status, _ = _http("POST", f"{e.base}/registry/agents",
                      {"agent_id": lookalike, "name": "r", "owner": "o", "domain": "finance"})
    assert status == 201
    for cmd in ("canary", "catalogue", "revoke"):
        extra = ("--expect-endpoint", "skipped") if cmd == "catalogue" else ()
        code, out = _run(e.argv(cmd, "--agent", lookalike, "--token", e.token, *extra))
        assert code == 2, (cmd, out)
    _, rec = _http("GET", f"{e.base}/registry/agents/{lookalike}")
    assert rec["status"] == "active" and rec.get("attested_at") is None


def test_b7_the_exact_canary_id_with_a_non_canary_domain_is_refused(estate):
    e = estate
    _http("PATCH", f"{e.base}/registry/agents/{CANARY}", {"domain": "finance"})
    code, _ = _run(e.argv("canary", "--agent", CANARY, "--token", e.token))
    assert code == 2


# --- B8: refused-kill can never fire at a real agent ---------------------------------------


def test_b8_refused_kill_refuses_any_target_that_is_not_the_retired_canary(estate):
    for target in ("ssl-invoicing-agent", CANARY):
        code, _ = _run(estate.argv("refused-kill", "--agent", target))
        assert code == 2


def test_b8_a_broken_retired_guard_only_ever_kills_the_retired_canary(estate):
    """The failure the check exists to catch: a kill-switch that treats a
    retired agent as active. The probe must report FAIL — and the only record
    it can have damaged is the retired canary."""
    estate.fault("ks_sees_retired_as_active")
    code, out = _run(estate.argv("refused-kill", "--agent", RETIRED))
    assert code == 1
    assert "refused 409" in out


# --- B9: health cannot pass on dead or open services ---------------------------------------


def test_b9_health_fails_when_a_data_route_is_dead_behind_a_healthy_health(estate):
    estate.fault("registry_data_500")
    code, out = _run(estate.argv("health"))
    assert code == 1
    assert "/registry/agents" in out


def test_b9_expect_perimeter_fails_when_any_service_is_open(secret_estate):
    secret_estate.fault("no_authn_except_registry")
    code, out = _run(secret_estate.argv("health", "--expect-perimeter"))
    assert code == 1


def test_b9_expect_perimeter_without_the_secret_is_a_failure(estate):
    code, out = _run(estate.argv("health", "--expect-perimeter"))
    assert code == 1


def test_b9_an_unknown_prefix_is_refused_and_no_checks_is_not_a_pass(estate):
    assert _run(estate.argv("health", "--only", "bogus"))[0] == 2


# --- fix-first: the remaining false greens ---------------------------------------------------


def test_f3_the_attest_drill_count_cannot_pass_as_zero_equals_zero(estate):
    estate.fault("attest_drills_zero")
    code, out = _catalogue(estate)
    assert code == 1
    # C4 (plan-named): the fault now zeroes the gate-verification row, where the canary's drill is counted
    assert "[FAIL] A2 gate-verification row 0 == recomputed canary events" in out, out


def test_f3b_the_governance_drill_count_must_equal_the_non_canary_drills(estate):
    estate.fault("attest_drills_off_by_one")
    code, out = _catalogue(estate)
    assert code == 1
    assert "[FAIL] A2 'Kill drills completed' " in out and "== recomputed non-canary drills" in out, out


def test_f3c_a_pack_that_ignores_the_window_fails(estate):
    estate.fault("attest_ignores_window")
    code, out = _catalogue(estate)
    assert code == 1
    assert "[FAIL] A2 windowed pack ?since=2026-01-01 served 200 as an unsigned range" in out, out
    assert "[FAIL] A2 a bad window (?period=2026-Q5) refused 422 (got 200)" in out, out


def _line(out: str, prefix: str) -> str:
    lines = [x for x in out.splitlines() if x.lstrip().startswith(prefix)]
    assert len(lines) == 1, (prefix, out)
    return lines[0].strip()


def test_f3d_a_gate_row_of_zero_against_zero_canary_events_is_not_a_pass(estate):
    """INF-1: the '>= 1' guard. A ledger that lost every canary event and a pack
    row of 0 agree (0 == 0) — the check must still FAIL, not pass vacuously."""
    estate.fault("canary_events_vanish", "attest_drills_zero")
    code, out = _catalogue(estate)
    assert code == 1
    line = _line(out, "[FAIL] A2 gate-verification row ")
    assert line == ("[FAIL] A2 gate-verification row 0 == recomputed canary events from the ledger "
                    "(between 0 read before and 0 after the pack; >= 1)"), out


def test_f3e_a_windowed_pack_passed_off_as_signed_fails(estate):
    """INF-1: the windowed pack's 'signed is False' check, alone (kind and since are right)."""
    estate.fault("attest_window_signed")
    code, out = _catalogue(estate)
    assert code == 1
    line = _line(out, "[FAIL] A2 windowed pack ?since=2026-01-01 ")
    assert "(got HTTP 200, kind=range, signed=True)" in line, out


def test_f3g_an_armed_signing_estate_serves_the_window_signed_and_that_passes(estate):
    """F4/A8: with /attest/health signing "on" the windowed pack is signed by the estate key, so the
    A2 window check expects signed=True. This was the standing false-red on both estates."""
    estate.fault("attest_signing_on")
    code, out = _catalogue(estate)
    line = _line(out, "[PASS] A2 windowed pack ?since=2026-01-01 ")
    assert "as a signed range" in line, out


def test_f3h_the_window_signed_expectation_follows_attest_health():
    expected_window_signed = estate_probe.expected_window_signed
    assert expected_window_signed({"signing": "on"}) is True
    for h in ({"signing": "off"}, {"signing": "error"}, {}, None, [], "on"):
        assert expected_window_signed(h) is False, h


def test_f3f_a_canary_event_landing_between_the_pack_and_the_ledger_reads_is_not_a_false_red(estate):
    """INF-1: the exact equality false-reds on a live estate. The bracket
    (before <= row <= after) passes an event appended after the pack; an
    inflated row still fails."""
    estate.fault("canary_event_after_pack")
    code, out = _catalogue(estate)
    line = _line(out, "[PASS] A2 gate-verification row ")
    before, after = (int(x) for x in line.split("(between ")[1].split(" after")[0].split(" read before and "))
    assert after == before + 1, line  # the interleaved append really landed between the reads
    assert code == 0, out
    estate.fault("attest_gate_overcount")
    code, out = _catalogue(estate)
    assert code == 1 and _line(out, "[FAIL] A2 gate-verification row "), out


def test_f4_a_checkin_that_is_not_stored_fails(estate):
    estate.fault("checkin_not_recorded")
    assert _catalogue(estate)[0] == 1


def test_f5_a_block_for_the_wrong_reason_is_not_kill_propagation(estate):
    estate.fault("sentinel_wrong_registry")
    assert _catalogue(estate)[0] == 1


def test_f6_the_endpoint_outcome_must_match_what_the_gate_expects(estate):
    code, out = _run(estate.argv("catalogue", "--agent", CANARY, "--token", estate.token,
                                 "--expect-endpoint", "called"))
    assert code == 1


# --- Phase C: every container reports the build-arg SHA the gate deployed with ------------


def test_c_expect_build_sha_passes_when_every_service_and_the_console_report_it(estate):
    code, out = _run(estate.argv("health", "--expect-build-sha", BUILD_SHA))
    assert code == 0, out
    passed = [line for line in out.splitlines() if line.startswith("  [PASS] ") and "build_sha" in line]
    assert len(passed) == len(estate_probe.SERVICES) + 1, out


def test_c_expect_build_sha_passes_on_the_secret_estate_with_the_perimeter(secret_estate):
    code, out = _run(secret_estate.argv("health", "--expect-perimeter", "--expect-build-sha", BUILD_SHA))
    assert code == 0, out


@pytest.mark.parametrize("stale", ["ledger", "attest", "console"])
def test_c_one_container_left_on_the_previous_image_fails(estate, stale):
    estate.fault(f"stale_build_sha_{stale}")
    code, out = _run(estate.argv("health", "--expect-build-sha", BUILD_SHA))
    assert code == 1
    path = "/health build_sha" if stale == "console" else f"/{stale}/health build_sha"
    assert f"[FAIL] {path}" in out


def test_c_a_different_deploy_sha_fails_every_service(estate):
    code, out = _run(estate.argv("health", "--expect-build-sha", "f" * 40))
    assert code == 1
    failed = [line for line in out.splitlines() if line.startswith("  [FAIL] ") and "build_sha" in line]
    assert len(failed) == len(estate_probe.SERVICES) + 1, out


@pytest.mark.parametrize("value", ["unknown", "", BUILD_SHA[:12], BUILD_SHA.upper(), BUILD_SHA + "0"])
def test_c_expect_build_sha_refuses_a_value_that_is_not_a_full_sha(estate, value):
    assert _run(estate.argv("health", "--expect-build-sha", value))[0] == 2


# --- registry: READ-ONLY listing -------------------------------------------------------------

#: Subcommands that never mutate. Pinned HERE and declared in estate_probe.READ_ONLY_SUBCOMMANDS:
#: widening the set needs a reviewed edit to both files (test_m_read_only_set_matches_the_tool).
READ_ONLY = frozenset({"health", "pin", "continuity", "collateral", "registry"})
#: Read-only handlers that may issue a non-GET, with the reason. Do not widen the rule instead.
#: health: its per-service data-route probe for `replay` is a POST of an EMPTY body to
#: /replay/replay, and "serving" means HTTP 422: the replay service validates the body and
#: rejects it before replaying anything, so nothing is written (test_m_health_probe_post_*
#: pins the route table and shows the ledger and registry unchanged afterwards).
READ_ONLY_NON_GET = {"health": "empty-body POST to /replay/replay expecting 422 (validation reject)"}
GUARD = "_require_canary"
GUARD_SETS = {"CANARIES", "RETIRED_CANARIES"}


def _module():
    import ast
    tree = ast.parse(Path(estate_probe.__file__).read_text(encoding="utf-8"))
    return tree, {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _module_assigns(tree, name):
    import ast
    return [n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
            and any(isinstance(t, ast.Name) and t.id == name
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))]


def _handler_table(tree, funcs):
    """The subcommand -> handler table, found BY NAME (HANDLERS), and checked to be the
    one main() dispatches through."""
    import ast
    found = _module_assigns(tree, "HANDLERS")
    assert len(found) == 1, "exactly one module-level HANDLERS assignment"
    d = found[0].value
    assert isinstance(d, ast.Dict) and all(isinstance(k, ast.Constant) for k in d.keys)
    assert all(isinstance(v, ast.Name) for v in d.values), "handlers must be plain function names"
    table = {k.value: v.id for k, v in zip(d.keys, d.values)}
    dispatch = [n for n in ast.walk(funcs["main"]) if isinstance(n, ast.Subscript)
                and isinstance(n.value, ast.Name) and n.value.id == "HANDLERS"]
    assert dispatch, "main() must dispatch through HANDLERS"
    return table


def _estate_calls_non_get(nodes, funcs, owner, seen=None):
    """[(function the call is in, method)] for every estate.call whose method is not the
    literal "GET", following calls to module functions transitively."""
    import ast
    seen = set() if seen is None else seen
    out = []
    for node in nodes:
        for c in ast.walk(node):
            if not isinstance(c, ast.Call):
                continue
            if isinstance(c.func, ast.Attribute) and c.func.attr == "call":
                arg = c.args[0] if c.args else next((k.value for k in c.keywords if k.arg == "method"), None)
                method = arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else "<non-literal>"
                if method != "GET":
                    out.append((owner, method))
            elif isinstance(c.func, ast.Name) and c.func.id in funcs and c.func.id not in seen:
                seen.add(c.func.id)
                out += _estate_calls_non_get(funcs[c.func.id].body, funcs, c.func.id, seen)
    return out


def test_m_canary_static_the_parsers_and_the_handler_table_agree():
    import ast
    tree, funcs = _module()
    table = _handler_table(tree, funcs)
    main = funcs["main"]
    parsers = {c.args[0].value for c in ast.walk(main) if isinstance(c, ast.Call)
               and isinstance(c.func, ast.Attribute) and c.func.attr == "add_parser"
               and c.args and isinstance(c.args[0], ast.Constant)}
    for loop in (n for n in ast.walk(main) if isinstance(n, ast.For) and isinstance(n.iter, ast.Tuple)):
        parsers |= {e.value for e in loop.iter.elts if isinstance(e, ast.Constant)}
    assert parsers == set(table), (parsers, set(table))
    assert set(table.values()) <= set(funcs)
    assert READ_ONLY <= set(table)


def test_m_read_only_set_matches_the_tool():
    import ast
    tree, funcs = _module()
    assert estate_probe.READ_ONLY_SUBCOMMANDS == READ_ONLY
    (decl,) = _module_assigns(tree, "READ_ONLY_SUBCOMMANDS")
    call = decl.value
    assert isinstance(call, ast.Call) and call.func.id == "frozenset" and isinstance(call.args[0], ast.Set)
    assert {e.value for e in call.args[0].elts} == READ_ONLY       # a literal, not computed
    assert set(READ_ONLY_NON_GET) <= READ_ONLY


def test_m_guard_sets_are_the_exact_canary_ids_and_assigned_once():
    tree, _ = _module()
    assert estate_probe.CANARIES == frozenset({"canary-gb10", "canary-fly"})
    assert estate_probe.RETIRED_CANARIES == frozenset({"canary-gb10-retired", "canary-fly-retired"})
    for name in GUARD_SETS:
        assert len(_module_assigns(tree, name)) == 1, f"{name} must be assigned exactly once"


def test_m_canary_static_every_mutating_handler_guards_first():
    """Every NON-read-only handler calls _require_canary(estate, agent[, allowed]) as an
    unconditional top-level statement of its body BEFORE any estate.call that is not a GET
    (transitively through helpers), and `allowed` can only be the module's own sets."""
    import ast
    tree, funcs = _module()
    table = _handler_table(tree, funcs)
    default = funcs[GUARD].args.defaults
    assert len(default) == 1 and isinstance(default[0], ast.Name) and default[0].id == "CANARIES"
    mutating = set(table) - READ_ONLY
    assert mutating == {"canary", "catalogue", "refused-kill", "revoke"}, mutating
    for cmd in sorted(mutating):
        body = funcs[table[cmd]].body
        idx = None
        for i, stmt in enumerate(body):          # top-level statements only: unconditional
            value = stmt.value if isinstance(stmt, (ast.Expr, ast.Assign)) else None
            if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == GUARD):
                idx = i
                break
        assert idx is not None, f"{cmd}: no unconditional top-level {GUARD}(...) statement"
        before = _estate_calls_non_get(body[:idx], funcs, table[cmd])
        assert not before, f"{cmd}: non-GET call(s) {before} before {GUARD}"
        call = body[idx].value
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == "estate"
        assert len(call.args) <= 3 and all(k.arg == "allowed" for k in call.keywords)
        allowed = call.args[2] if len(call.args) > 2 else next((k.value for k in call.keywords), None)
        want = "RETIRED_CANARIES" if cmd == "refused-kill" else "CANARIES"
        if allowed is None:
            assert want == "CANARIES", f"{cmd} must pass allowed=RETIRED_CANARIES"
        else:
            assert isinstance(allowed, ast.Name) and allowed.id == want, f"{cmd}: allowed must be {want}"


def test_m_canary_static_read_only_handlers_issue_only_gets():
    tree, funcs = _module()
    table = _handler_table(tree, funcs)
    for cmd in sorted(READ_ONLY):
        fn = table[cmd]
        import ast
        calls = {c.func.id for c in ast.walk(funcs[fn]) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        assert GUARD not in calls, f"{cmd} is READ_ONLY but calls {GUARD}"
        non_get = _estate_calls_non_get(funcs[fn].body, funcs, fn)
        if cmd in READ_ONLY_NON_GET:
            assert non_get and all(owner == fn for owner, _ in non_get), (cmd, non_get)
        else:
            assert not non_get, f"{cmd} is READ_ONLY but issues {non_get}"


def test_m_health_probe_post_is_only_the_422_replay_route():
    """health's one non-GET is the DATA_ROUTES method: exactly one POST route, replay, and it
    counts as "serving" only on 422 (the body is rejected before anything is replayed)."""
    posts = {p for p, (m, _, _) in estate_probe.DATA_ROUTES.items() if m != "GET"}
    assert posts == {"replay"}
    assert estate_probe.DATA_ROUTES["replay"] == ("POST", "/replay/replay", (422,))


def test_m_health_changes_nothing_on_the_estate(estate):
    ledger_before = _http("GET", f"{estate.base}/ledger/health")[1]
    events_before = _http("GET", f"{estate.base}/ledger/events")[1]
    agents_before = _http("GET", f"{estate.base}/registry/agents")[1]
    assert _run(estate.argv("health"))[0] == 0
    assert _http("GET", f"{estate.base}/ledger/health")[1] == ledger_before
    assert _http("GET", f"{estate.base}/ledger/events")[1] == events_before
    assert _http("GET", f"{estate.base}/registry/agents")[1] == agents_before


def test_registry_lists_ids_domain_and_status_only(estate):
    code, out = _run(estate.argv("registry"))
    assert code == 0, out
    assert f"{CANARY} canary active" in out and f"{RETIRED} canary retired" in out, out
    for line in out.splitlines()[1:]:
        assert len(line.split()) == 3, line  # id domain status, nothing else


def test_registry_never_prints_a_token_or_other_fields(estate, secret_estate):
    for e in (estate, secret_estate):
        code, out = _run(e.argv("registry"))
        assert code == 0, out
        assert e.token not in out and "token" not in out.lower()
        assert SECRET not in out
        for other in ("owner", "FIELD canary", "attested_at", "created_at"):
            assert other not in out, (other, out)


def test_registry_agent_present_exits_0_with_status(estate):
    code, out = _run(estate.argv("registry", "--agent", CANARY))
    assert code == 0 and out.strip() == f"PRESENT {CANARY} status=active", out
    code, out = _run(estate.argv("registry", "--agent", RETIRED))
    assert code == 0 and out.strip() == f"PRESENT {RETIRED} status=retired", out


def test_registry_agent_absent_exits_1_and_matches_the_exact_id(estate):
    for missing in ("no-such-agent", "canary-gb1", CANARY.upper(), CANARY + "-x"):
        code, out = _run(estate.argv("registry", "--agent", missing))
        assert code == 1 and out.startswith("ABSENT "), (missing, out)


def test_registry_is_read_only_and_changes_nothing(estate):
    ledger_before = _http("GET", f"{estate.base}/ledger/health")[1]
    agents_before = _http("GET", f"{estate.base}/registry/agents")[1]
    assert _run(estate.argv("registry"))[0] == 0
    assert _run(estate.argv("registry", "--agent", CANARY))[0] == 0
    assert _http("GET", f"{estate.base}/ledger/health")[1] == ledger_before
    assert _http("GET", f"{estate.base}/registry/agents")[1] == agents_before


def test_registry_unreadable_is_exit_3_never_absent(estate):
    estate.fault("registry_data_500")
    for extra in (["--agent", CANARY], ["--agent", "no-such-agent"], []):
        code, out = _run(estate.argv("registry", *extra))
        assert code == 3 and "UNREADABLE" in out and "ABSENT" not in out and "PRESENT" not in out, out


def test_registry_sends_the_perimeter_secret_and_never_prints_it(secret_estate, monkeypatch):
    code, out = _run(secret_estate.argv("registry", "--agent", CANARY))
    assert code == 0 and SECRET not in out, out
    # without the secret the perimeter refuses (401): unreadable (3), never "absent" (1)
    monkeypatch.delenv("FIELD_SHARED_SECRET")
    code, out = _run(secret_estate.argv("registry", "--agent", CANARY))
    assert code == 3 and "ABSENT" not in out, out


# --- registry: fault cases against a scripted server -------------------------------------------


class _Scripted:
    """A one-route HTTP server that answers GET /registry/agents with a scripted reply and
    records every request, so a test can see what the probe sent (and that it never followed
    a redirect or sent anything but GET)."""

    def __init__(self, status=200, body=b"[]", headers=None, need_secret=None):
        import http.server
        import threading
        outer = self
        self.requests: list[tuple[str, str]] = []

        class H(http.server.BaseHTTPRequestHandler):
            def _answer(self):
                outer.requests.append((self.command, self.path))
                if need_secret is not None and self.headers.get("x-field-auth") != need_secret:
                    self.send_response(401)
                    payload = b'{"detail": "unauthorised"}'
                else:
                    self.send_response(status)
                    for k, v in (headers or {}).items():
                        self.send_header(k, v)
                    payload = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _answer

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def argv(self, *rest):
        return ["--base", self.base, *rest]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture()
def scripted(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    made: list[_Scripted] = []

    def make(**kw):
        s = _Scripted(**kw)
        made.append(s)
        return s
    yield make
    for s in made:
        s.close()


def _row(agent_id, domain="canary", status="active", **extra):
    return {"agent_id": agent_id, "domain": domain, "status": status, **extra}


#: (id, scripted reply, extra argv) -> every one must exit 3 and never say ABSENT/PRESENT
_UNREADABLE = [
    ("http-500", dict(status=500, body={"detail": "boom"}), ["--agent", "a"]),
    ("http-500-list", dict(status=500, body={"detail": "boom"}), []),
    ("http-404", dict(status=404, body={"detail": "nope"}), ["--agent", "a"]),
    ("redirect-302", dict(status=302, body=b"", headers={"Location": "/elsewhere"}), ["--agent", "a"]),
    ("redirect-301-list", dict(status=301, body=b"", headers={"Location": "/elsewhere"}), []),
    ("200-dict-body", dict(body={"agents": [_row("a")]}), ["--agent", "a"]),
    ("200-dict-body-list", dict(body={"agents": []}), []),
    ("200-string-body", dict(body="nope"), ["--agent", "a"]),
    ("200-number-body", dict(body=5), ["--agent", "a"]),
    ("200-null-body", dict(body=b"null"), ["--agent", "a"]),
    ("200-not-json", dict(body=b"<html>not json</html>"), ["--agent", "a"]),
    ("200-empty-body", dict(body=b""), ["--agent", "a"]),
    ("non-dict-row-string", dict(body=[_row("a"), "oops"]), ["--agent", "a"]),
    ("non-dict-row-string-absent", dict(body=[_row("b"), "oops"]), ["--agent", "a"]),
    ("non-dict-row-null", dict(body=[None, _row("a")]), ["--agent", "a"]),
    ("non-dict-row-list-mode", dict(body=[_row("a"), 7]), []),
    ("non-dict-row-nested-list", dict(body=[[_row("a")]]), []),
    ("duplicate-id", dict(body=[_row("a"), _row("b"), _row("a", status="retired")]), ["--agent", "a"]),
    ("null-status", dict(body=[_row("a", status=None)]), ["--agent", "a"]),
    ("dict-status", dict(body=[_row("a", status={"x": 1})]), ["--agent", "a"]),
    ("status-with-space", dict(body=[_row("a", status="active x")]), ["--agent", "a"]),
]


@pytest.mark.parametrize("name,reply,extra", _UNREADABLE, ids=[c[0] for c in _UNREADABLE])
def test_registry_fault_is_exit_3_never_absent_or_present(scripted, name, reply, extra):
    s = scripted(**reply)
    code, out = _run(s.argv("registry", *extra))
    assert code == 3, (name, code, out)
    assert out.startswith("UNREADABLE "), out
    assert "ABSENT" not in out and "PRESENT" not in out, out
    assert s.requests == [("GET", "/registry/agents")], s.requests   # one GET, no redirect followed


def test_registry_401_with_the_wrong_secret_is_exit_3(scripted, monkeypatch):
    s = scripted(need_secret="the-right-secret-value")
    monkeypatch.setenv("FIELD_SHARED_SECRET", "a-wrong-secret-value")
    for extra in (["--agent", "a"], []):
        code, out = _run(s.argv("registry", *extra))
        assert code == 3 and "HTTP 401" in out and "ABSENT" not in out, out
        assert "a-wrong-secret-value" not in out and "the-right-secret-value" not in out


def test_registry_transport_error_is_exit_3(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    base = f"http://127.0.0.1:{_free_port()}"            # nothing listens here
    for extra in (["--agent", "a"], []):
        code, out = _run(["--base", base, "registry", *extra])
        assert code == 3 and "HTTP 0" in out and "ABSENT" not in out, out


def test_registry_absent_is_exit_1_only_after_a_good_read(scripted):
    for body in ([], [_row("b")], [_row("b"), _row("c", domain="finance")]):
        s = scripted(body=body)
        code, out = _run(s.argv("registry", "--agent", "a"))
        assert code == 1 and out.strip() == "ABSENT a", (body, code, out)


def test_registry_present_is_exit_0(scripted):
    s = scripted(body=[_row("b"), _row("a", status="active")])
    code, out = _run(s.argv("registry", "--agent", "a"))
    assert code == 0 and out.strip() == "PRESENT a status=active", out


def test_registry_duplicate_message_names_the_count_and_not_the_other_fields(scripted):
    s = scripted(body=[_row("a", owner="secret-owner"), _row("a", owner="other")])
    code, out = _run(s.argv("registry", "--agent", "a"))
    assert code == 3 and "2 times" in out and "ambiguous" in out and "owner" not in out, out


_BAD_IDS = [
    ("empty", ""), ("space", "a b"), ("leading-space", " a"), ("trailing-space", "a "),
    ("newline", "a\nb"), ("tab", "a\tb"), ("cr", "a\rb"), ("nul", "a\x00b"), ("escape", "\x1b[31ma"),
    ("del", "a\x7fb"), ("non-ascii", "café"), ("nbsp", "a b"),
    ("129-chars", "a" * 129), ("1000-chars", "a" * 1000),
]


@pytest.mark.parametrize("name,bad", _BAD_IDS, ids=[c[0] for c in _BAD_IDS])
def test_registry_agent_with_an_unsafe_id_is_a_usage_error_before_any_request(scripted, name, bad):
    s = scripted(body=[_row("a")])
    code, out = _run(s.argv("registry", "--agent", bad))
    assert code == 2 and "refusing:" in out, (name, code, out)
    assert "ABSENT" not in out and "PRESENT" not in out
    assert not bad or bad not in out                         # the unsafe id is never echoed
    assert s.requests == []                                 # refused before touching the estate


def test_registry_agent_at_the_128_char_limit_is_accepted(scripted):
    ident = "a" * 128
    s = scripted(body=[_row(ident)])
    code, out = _run(s.argv("registry", "--agent", ident))
    assert code == 0 and out.strip() == f"PRESENT {ident} status=active", out


def test_registry_listing_never_renders_whitespace_in_an_id_as_extra_columns(scripted):
    s = scripted(body=[_row("x canary active"), _row("tab\tid", domain="a\nb"),
                       _row("ok-id", domain="\x1b[31mred", status="s" * 129),
                       _row("n" * 129), _row("café")])
    code, out = _run(s.argv("registry"))
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "registry - 5 agents (id domain status)" and len(lines) == 6, out
    for line in lines[1:]:
        assert len(line.split()) == 3, line                  # id domain status, no fake columns
    assert "x canary active" not in out and "\x1b" not in out and "\t" not in out
    assert "<str-unsafe:len=15>" in out and "ok-id" in out


def test_registry_listing_with_a_null_status_shows_a_placeholder(scripted):
    s = scripted(body=[_row("a", status=None)])
    code, out = _run(s.argv("registry"))
    assert code == 0 and "a canary <NoneType>" in out, out


def test_shape_masks_unsafe_key_names():
    assert estate_probe._shape({"ok": 1, "b": 2}) == "dict keys=b,ok"
    hostile = {"evil key\ninjected line": 1, "\x1b[31mred": 2, "k" * 129: 3, "café": 4, "": 5, "fine": 6}
    shown = estate_probe._shape(hostile)
    assert shown == "dict keys=" + ",".join(sorted(["<unsafe-key>"] * 5 + ["fine"]))
    assert "\n" not in shown and "\x1b" not in shown and " " not in shown.split(" ", 1)[1]
    assert estate_probe._shape({str(i): i for i in range(30)}).count(",") == 11      # still capped at 12


def test_a_200_dict_body_with_hostile_keys_prints_only_masked_names(scripted):
    s = scripted(body={"x\ncanary-gb10 PRESENT status=active": 1, "keep": 2})
    code, out = _run(s.argv("registry", "--agent", "a"))
    assert code == 3, out
    assert "canary-gb10 PRESENT" not in out and len(out.strip().splitlines()) == 1, out
    assert "dict keys=<unsafe-key>,keep" in out


def test_plain_masks_whitespace_control_length_and_non_text():
    plain = estate_probe._plain
    assert plain("canary-gb10") == "canary-gb10" and plain("a" * 128) == "a" * 128
    for bad in ("a b", "a\tb", "a\nb", "", "a" * 129, "\x1b[0m", "café"):
        shown = plain(bad)
        assert shown.startswith("<str-unsafe:len=") and not any(c.isspace() for c in shown), shown
    assert plain(None) == "<NoneType>" and plain(5) == "<int>" and plain({"k k": 1}) == "<dict keys=<unsafe-key>>"
