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

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import estate_probe  # noqa: E402

CANARY_MANIFEST = REPO / "manifests" / "canary-gb10.yaml"
HARNESS = Path(__file__).with_name("estate_harness.py")
SECRET = "estate-probe-test-secret-never-printed"
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
        argv = [sys.executable, str(HARNESS), str(self.port), str(data)]
        if secret:
            argv.append("--secret")
            self.env["FIELD_SHARED_SECRET"] = SECRET
        self.proc = subprocess.Popen(argv, env=self.env, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        deadline = time.time() + 60
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


# --- B4: a drill must actually restore the canary ----------------------------------------


def test_b4_catalogue_fails_when_a_drill_leaves_the_canary_killed(estate):
    estate.fault("drill_leaves_killed")
    code, _ = _catalogue(estate)
    assert code == 1


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
    assert _catalogue(estate)[0] == 1


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
