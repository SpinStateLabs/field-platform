"""phase_g_check is the live verifier of Phase G operator auth, run against production canaries.

If it can report PASS on a broken estate, Phase G is declared verified when it
is not. So every test here drives the REAL services over real HTTP
(estate_harness.py mounts each service's create_app() under the Caddy prefixes,
with the Phase G flags flipped at runtime through /__operator) and asserts BOTH
directions: the tool passes on a healthy estate in each mode, and goes red on
the exact breakage each check exists to catch (the fault tests). The tool's
safety properties are tests too: it refuses any non-canary agent before
sending anything, never un-kills a halted canary, and never prints the key,
its hash or the perimeter secret.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).parent))

import estate_probe  # noqa: E402
import phase_g_check  # noqa: E402
from test_estate_probe import CANARY, SECRET, Estate, _http  # noqa: E402

# Settle windows are for a live estate's asynchronous append; the test estate is local. Every fault test and
# every "left NO event" check waits out the whole window (a negative cannot return early), so it is the floor
# of this file's run time. 1.5 s is the service's own bound on that append (LEDGER_APPEND_TIMEOUT_S): the
# request has already waited that long before it answers, and a local ledger writes in milliseconds (C-328).
SETTLE_S = 1.5   # applied per module by `_settle_window` below

KEY_DON = "fok_don-test-key-NEVER-PRINT_0123456789abcdef"
KEY_OTHER = "fok_other-test-key-NEVER-PRINT_fedcba9876543210"
KEY_SVC = "fok_svc-test-key-NEVER-PRINT_aaaaaaaaaaaaaaaa"
FP_DON = hashlib.sha256(KEY_DON.encode()).hexdigest()[:8]


def _row(oid: str, key: str, scopes: list[str], names: list[str] | None = None, **kw) -> dict:
    return {"operator_id": oid, "key_sha256": hashlib.sha256(key.encode()).hexdigest(), "status": "active",
            "created_at": "2026-10-01T00:00:00+00:00", "scopes": scopes, "names": names or [], **kw}


@pytest.fixture(autouse=True, scope="module")
def _settle_window():
    """This module's settle window, set for its tests only. A bare module-level assignment is shared by every
    module of the run and the last one imported wins, so the saving (or the margin) held only when the file ran
    alone (C-340, reviewer C-335 F-C335-1)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(phase_g_check, "SETTLE_S", SETTLE_S)
        yield


@pytest.fixture(scope="module")
def est(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("phase_g")
    # The harness's internal HTTP clients capture auth_headers() when first used, so the
    # service identity must be in the harness's environment AT BOOT (mode off ignores it).
    # It is removed from this process again straight away.
    saved = {k: os.environ.get(k) for k in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY")}
    os.environ.update(FIELD_OPERATOR="svc", FIELD_OPERATOR_KEY=KEY_SVC)
    try:
        e = Estate(tmp, secret=True)
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    e.ops_file = tmp / "operators.json"
    e.ops_file.write_text(json.dumps([
        _row("don", KEY_DON, ["*"], ["Don Hagell, Spin State Labs"]),
        _row("other", KEY_OTHER, ["*"]),
        _row("svc", KEY_SVC, ["*", "bypass_operator_list", "ledger_attribute"],
             event_prefixes=["kill.", "registry.", "debug."]),
    ]))
    e.secret_file = tmp / "perimeter.secret"
    e.secret_file.write_text(SECRET + "\n")
    e.key_file = tmp / "don.key"
    e.key_file.write_text(KEY_DON + "\n")
    e.other_key_file = tmp / "other.key"
    e.other_key_file.write_text(KEY_OTHER + "\n")
    try:
        yield e
    finally:
        _arm(e, "off")
        e.close()


def _arm(e: Estate, mode: str) -> None:
    env: dict[str, str | None] = {"FIELD_OPERATOR_REGISTRY": None, "FIELD_OPERATOR_REQUIRE": None}
    if mode != "off":
        env["FIELD_OPERATOR_REGISTRY"] = str(e.ops_file)
    if mode == "enforce":
        env["FIELD_OPERATOR_REQUIRE"] = "1"
    status, _ = _http("POST", f"{e.base}/__operator", {"env": env})
    assert status == 200


@pytest.fixture
def estate(est):
    _arm(est, "off")
    est.reset()
    yield est
    _arm(est, "off")
    est.reset()


def run(e: Estate, *rest: str, keyed: bool = False, key_file: Path | None = None, secret: bool = True,
        infer: bool = False):
    """``infer=True`` runs WITHOUT --expect-mode (C-122: an unasserted OFF is a FAIL). Every other test of
    this module states the mode it expects; one that does not is on the OFF estate and says so here."""
    if not infer and "--expect-mode" not in rest and "--restore" not in rest:
        rest = ("--expect-mode", "off", *rest)
    argv = ["--base", e.base, *rest]
    if secret:
        argv += ["--secret-file", str(e.secret_file)]
    if keyed:
        argv += ["--operator-id", "don", "--key-file", str(key_file or e.key_file)]
    out = io.StringIO()
    saved = sys.stdout, sys.stderr
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = phase_g_check.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    sys.stdout, sys.stderr = saved
    return code, out.getvalue()


def events(e: Estate, **params) -> list[dict]:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    status, body = _http("GET", f"{e.base}/ledger/events" + (f"?{q}" if q else ""), None, SECRET)
    assert status == 200
    return body


def canary_killed(e: Estate) -> bool:
    status, hb = _http("GET", f"{e.base}/killswitch/heartbeat/{CANARY}", None, SECRET)
    return hb["killed"]


def failed(out: str) -> list[str]:
    return [ln.strip() for ln in out.splitlines() if "[FAIL]" in ln]


def red(code: int, out: str, needle: str) -> None:
    """The run went RED, and on the check that names `needle`."""
    assert code == 1, out
    assert any(needle in ln for ln in failed(out)), f"expected a FAIL mentioning {needle!r}:\n{out}"


def assert_secret_free(out: str) -> None:
    for secret in (KEY_DON, KEY_OTHER, KEY_SVC, SECRET, hashlib.sha256(KEY_DON.encode()).hexdigest(), FP_DON):
        assert secret not in out, "a secret reached the tool output"


# --- healthy estates, every mode ------------------------------------------------------


def test_off_mode_is_inferred_and_changes_nothing(estate):
    code, out = run(estate, "--expect-mode", "off")
    assert code == 0, out
    assert "inferred mode: off" in out and "mode off: the guard is not armed" in out
    assert events(estate, event_type="operator.unauthenticated") == []
    assert not canary_killed(estate)
    assert_secret_free(out)


def test_enforce_without_credentials_every_refusal_changes_nothing(estate):
    _arm(estate, "enforce")
    revives_before = len(events(estate, event_type="kill.revive", agent_id=CANARY))
    kills_before = len(events(estate, event_type="kill.agent", agent_id=CANARY))
    code, out = run(estate, "--expect-mode", "enforce")
    assert code == 0, out
    for want in ("inferred mode: enforce", "=> HTTP 401", "=> HTTP 403", "=> HTTP 400",
                 "byte-identical", "malformed: duplicate x-field-operator headers",
                 "malformed: non-ASCII operator id", "over-long key (257 chars)",
                 "an alias / display name used as the login id"):
        assert want in out, want
    # every enforce probe was REFUSED: the ledger saw neither a kill nor a revive
    assert len(events(estate, event_type="kill.revive", agent_id=CANARY)) == revives_before
    assert len(events(estate, event_type="kill.agent", agent_id=CANARY)) == kills_before
    assert not canary_killed(estate)
    assert "positive path: skipped" in out
    assert_secret_free(out)


def test_enforce_with_a_key_runs_the_positive_path_and_attributes_it(estate):
    _arm(estate, "enforce")
    k0 = len(events(estate, event_type="kill.agent", agent_id=CANARY))
    r0 = len(events(estate, event_type="kill.revive", agent_id=CANARY))
    code, out = run(estate, "--expect-mode", "enforce", keyed=True)
    assert code == 0, out
    assert "kill with your credentials => 200" in out and "revive with your credentials => 200" in out
    assert "id/key mismatch" in out
    [kill] = events(estate, event_type="kill.agent", agent_id=CANARY)[k0:]
    [revive] = events(estate, event_type="kill.revive", agent_id=CANARY)[r0:]
    for ev in (kill, revive):
        assert ev["payload"]["operator_id_authenticated"] == "don"
        assert ev["payload"]["operator_claimed"] == "don"
        assert ev["payload"]["operator_key_fp"] == FP_DON
    assert not canary_killed(estate)               # revived
    assert_secret_free(out)


def test_log_only_without_credentials_is_allowed_unattributed_and_ledgered(estate):
    _arm(estate, "log-only")
    u0 = len(events(estate, event_type="operator.unauthenticated"))
    r0 = len(events(estate, event_type="kill.revive", agent_id=CANARY))
    code, out = run(estate, "--expect-mode", "log-only")
    assert code == 0, out
    assert "inferred mode: log-only" in out
    assert "left exactly one operator.unauthenticated event" in out
    unauth = events(estate, event_type="operator.unauthenticated")[u0:]
    assert {e["payload"]["reason"] for e in unauth} >= {"no_credential", "incomplete_credential", "bad_credential"}
    for ev in events(estate, event_type="kill.revive", agent_id=CANARY)[r0:]:
        assert ev["payload"]["operator_id_authenticated"] is None   # nothing was attributed
    assert not canary_killed(estate)
    assert_secret_free(out)


def test_log_only_with_a_key_attributes_the_positive_path(estate):
    _arm(estate, "log-only")
    k0 = len(events(estate, event_type="kill.agent", agent_id=CANARY))
    code, out = run(estate, "--expect-mode", "log-only", keyed=True)
    assert code == 0, out
    mine = events(estate, event_type="kill.agent", agent_id=CANARY)[k0:]
    assert len(mine) == 1 and mine[0]["payload"]["operator_key_fp"] == FP_DON
    assert_secret_free(out)


def test_expect_mode_mismatch_is_red(estate):
    code, out = run(estate, "--expect-mode", "enforce")      # the estate is OFF
    red(code, out, "estate mode is enforce as expected")


def test_a_user_supplied_alias_that_is_a_valid_id_charset_is_rejected_403(estate):
    _arm(estate, "enforce")
    code, out = run(estate, "--expect-mode", "enforce", "--alias", "Don.Hagell", keyed=True)
    assert code == 0, out
    # 403 bodies: unknown id, second unknown id/own id, mismatch, alias -> all one body
    assert "byte-identical" in out and "1 distinct" in out


# --- safety properties ---------------------------------------------------------------------


def test_a_non_canary_agent_is_refused_before_anything_is_sent(estate):
    for agent in ("agent-prod-1", "canary-evil", "canary-gb10-retired", "CANARY-GB10"):
        before = len(events(estate))
        code, out = run(estate, "--agent", agent)
        assert code == 2, (agent, out)
        assert "refusing" in out
        assert len(events(estate)) == before, "a refused run wrote to the ledger"


#: A canary-DOMAIN agent whose id is not canary-gb10 / canary-fly: the registry-domain check accepts it,
#: so only the exact-id allowlist (tool level, and estate_probe._require_canary) can refuse it.
LOOKALIKE = "canary-gb10-shadow"
TOOL_ALLOWLIST_REFUSAL = (f"'{LOOKALIKE}' is not one of ['canary-fly', 'canary-gb10'] - "
                          "this tool mutates the canary only (rule 7)")


def _register_lookalike(e: Estate) -> None:
    status, _ = _http("POST", f"{e.base}/registry/agents",
                      {"agent_id": LOOKALIKE, "name": "lookalike", "owner": "FIELD canary", "domain": "canary"},
                      SECRET)
    assert status in (201, 409), status            # the estate is shared by the module
    # the registry-domain layer on its own ACCEPTS it (that layer is not what refuses it below)
    rec = estate_probe._require_canary(estate_probe.Estate(e.base, SECRET), LOOKALIKE, frozenset({LOOKALIKE}))
    assert rec["agent_id"] == LOOKALIKE and rec["domain"] == "canary"


def _count_requests(monkeypatch) -> list[str]:
    """Every request either sender makes from here on (method and path)."""
    seen: list[str] = []
    real_call, real_send = estate_probe.Estate.call, phase_g_check.Sender.send

    def call(self, method, path, *a, **kw):
        seen.append(f"{method} {path}")
        return real_call(self, method, path, *a, **kw)

    def send(self, method, path, *a, **kw):
        seen.append(f"{method} {path}")
        return real_send(self, method, path, *a, **kw)
    monkeypatch.setattr(estate_probe.Estate, "call", call)
    monkeypatch.setattr(phase_g_check.Sender, "send", send)
    return seen


def test_a_canary_domain_lookalike_is_refused_by_the_exact_id_allowlist_before_any_request(estate, monkeypatch):
    _register_lookalike(estate)
    before = len(events(estate))
    seen = _count_requests(monkeypatch)
    code, out = run(estate, "--agent", LOOKALIKE)
    assert code == 2, out
    assert TOOL_ALLOWLIST_REFUSAL in out, out      # the tool's own allowlist, not the domain / 404 refusal
    assert seen == [], f"a refused run sent requests (the registry read included): {seen}"
    assert len(events(estate)) == before


def test_estate_probe_require_canary_alone_refuses_the_lookalike_before_any_request(estate, monkeypatch):
    _register_lookalike(estate)
    seen = _count_requests(monkeypatch)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        with pytest.raises(SystemExit) as exc:
            estate_probe._require_canary(estate_probe.Estate(estate.base, SECRET), LOOKALIKE)
    assert exc.value.code == 2
    assert f"'{LOOKALIKE}' is not one of ['canary-fly', 'canary-gb10']" in out.getvalue()
    assert seen == [], f"the registry was read before the allowlist refused: {seen}"


def test_an_agent_that_is_not_in_the_canary_domain_is_refused(estate):
    status, _ = _http("PATCH", f"{estate.base}/registry/agents/{CANARY}", {"domain": "prod"}, SECRET)
    assert status == 200
    before = len(events(estate))
    code, out = run(estate)
    assert code == 2 and "not a 'canary'-domain canary" in out
    assert len(events(estate)) == before


def test_a_killed_canary_is_not_probed_and_restore_revives_it(estate):
    status, _ = _http("POST", f"{estate.base}/killswitch/kill/{CANARY}",
                      {"operator": "test", "reason": "halted on purpose"}, SECRET)
    assert status == 200
    before = len(events(estate))
    code, out = run(estate)
    assert code == 2 and "is not active" in out
    assert canary_killed(estate) and len(events(estate)) == before     # nothing un-killed it
    code, out = run(estate, "--restore")
    assert code == 0, out
    assert not canary_killed(estate)
    assert "restart canary-agent" in out and "never runs docker" in out


def test_restore_in_enforce_needs_and_uses_the_operator_credentials(estate):
    _http("POST", f"{estate.base}/killswitch/kill/{CANARY}", {"operator": "test", "reason": "x"}, SECRET)
    _arm(estate, "enforce")
    code, out = run(estate, "--restore")                  # no credentials: refused 401
    red(code, out, "revive => 200")
    assert canary_killed(estate)
    code, out = run(estate, "--restore", keyed=True)
    assert code == 0, out
    assert not canary_killed(estate)
    assert_secret_free(out)


def test_usage_errors_exit_2(estate):
    assert run(estate, "--operator-id", "don")[0] == 2                      # id without a key
    assert run(estate, "--key-file", str(estate.key_file))[0] == 2          # key without an id
    bad = estate.key_file.with_name("bad.key")
    bad.write_text("has spaces in it")
    code, out = run(estate, keyed=True, key_file=bad)
    assert code == 2 and "has spaces" not in out
    assert run(estate, "--operator-id", "do n", "--key-file", str(estate.key_file))[0] == 2


def test_cleartext_to_a_public_host_with_the_secret_is_refused(est):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        with pytest.raises(SystemExit) as exc:
            phase_g_check.main(["--base", "http://8.8.8.8:8080", "--secret-file", str(est.secret_file)])
    assert exc.value.code == 2 and "cleartext" in out.getvalue()


def test_key_and_hash_never_reach_stdout_stderr_or_logs(estate, capsys, caplog):
    _arm(estate, "enforce")
    caplog.set_level("DEBUG")
    code, out = run(estate, "--expect-mode", "enforce", keyed=True)
    assert code == 0, out
    seen = out + capsys.readouterr().out + capsys.readouterr().err + caplog.text
    assert_secret_free(seen)
    # nor the made-up keys (they are random per run, so check by shape)
    assert "fok_probe_" not in out


def test_argv_never_carries_the_key_and_there_is_no_key_option():
    p = phase_g_check.build_parser()
    opts = {o for a in p._actions for o in a.option_strings}
    assert "--key" not in opts and "--operator-key" not in opts and "--key-file" in opts
    assert "--help" in opts


def test_help_text_is_accurate(capsys):
    with pytest.raises(SystemExit) as exc:
        phase_g_check.main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    for want in ("--base", "--secret-file", "--operator-id", "--key-file", "--expect-mode",
                 "off,log-only,enforce", "--agent", "--restore", "canary-gb10"):
        assert want in help_text, want
    assert phase_g_check.__doc__ and "never in a URL" in phase_g_check.__doc__


# --- fault injection: each check goes RED on the breakage it exists to catch -----------------


def test_FAULT_a_proxy_that_strips_the_credential_fails_the_wrong_key_checks(estate):
    _arm(estate, "enforce")
    estate.fault("strip_operator_headers")
    code, out = run(estate, keyed=True)
    # everything arrives anonymous => 401 where a 403 is the contract; and the positive path is refused
    red(code, out, "=> HTTP 401 (want 403)")
    assert any("kill with your credentials" in ln for ln in failed(out))


def test_FAULT_a_fail_open_guard_that_answers_403_as_200_is_red(estate):
    _arm(estate, "enforce")
    estate.fault("fail_open_403")
    code, out = run(estate, keyed=True)
    red(code, out, "=> HTTP 200 (want 403)")


def test_FAULT_malformed_headers_accepted_is_red(estate):
    _arm(estate, "enforce")
    estate.fault("fail_open_400")
    code, out = run(estate)
    red(code, out, "malformed: duplicate x-field-operator headers => HTTP 200 (want 400)")


def test_FAULT_a_403_body_that_names_the_cause_is_an_oracle_and_red(estate):
    _arm(estate, "enforce")
    estate.fault("forbidden_oracle")
    code, out = run(estate)
    red(code, out, "byte-identical")


def test_FAULT_a_reflected_key_in_a_response_body_is_red_and_not_printed(estate):
    _arm(estate, "enforce")
    estate.fault("revive_echo_headers")
    code, out = run(estate, keyed=True)
    red(code, out, "no key, key hash, perimeter secret or made-up key in any response body")
    assert "operator key found in the response body" in out
    assert_secret_free(out)                        # named by kind, never by value


def test_FAULT_a_missing_operator_unauthenticated_event_is_red_in_log_only(estate):
    _arm(estate, "log-only")
    estate.fault("ledger_drops_unauth")
    code, out = run(estate)
    red(code, out, "operator.unauthenticated")


def test_FAULT_an_anonymous_write_that_is_not_ledgered_is_red_in_log_only(estate):
    _arm(estate, "log-only")
    estate.fault("ledger_drops_nocred_unauth")
    code, out = run(estate)
    red(code, out, "left exactly one operator.unauthenticated event")


def test_FAULT_a_ledger_that_loses_the_key_fingerprint_is_red(estate):
    _arm(estate, "enforce")
    estate.fault("ledger_drops_fp")
    code, out = run(estate, keyed=True)
    red(code, out, "kill.agent carries")


def test_FAULT_a_wrong_key_fingerprint_is_red(estate):
    _arm(estate, "enforce")
    estate.fault("ledger_wrong_fp")
    code, out = run(estate, keyed=True)
    red(code, out, "kill.revive carries")
    assert "does NOT match" in out


def test_FAULT_the_key_leaking_into_a_ledger_payload_is_red(estate):
    _arm(estate, "enforce")
    estate.fault("key_into_ledger")
    code, out = run(estate, keyed=True)
    red(code, out, "ledger events since the start hold no key")
    assert_secret_free(out)


def test_FAULT_a_refusal_that_still_writes_is_red(estate):
    _arm(estate, "enforce")
    estate.fault("refusal_still_writes")
    code, out = run(estate)
    red(code, out, "wrote no kill.revive (refusal changed nothing)")


def test_FAULT_a_write_to_a_non_canary_agent_is_collateral_and_red(estate):
    _arm(estate, "log-only")
    estate.fault("collateral_event")
    code, out = run(estate, "--expect-mode", "log-only")
    red(code, out, "bystander.touched for agent-bystander")
    # ... and --allow makes the same event intended
    estate.reset()
    estate.fault("collateral_event")
    code, out = run(estate, "--expect-mode", "log-only", "--allow", "agent-bystander:bystander.touched")
    assert code == 0, out


def test_FAULT_a_kill_that_answers_200_without_halting_is_red(estate):
    _arm(estate, "enforce")
    estate.fault("kill_200_noflip")
    code, out = run(estate, keyed=True)
    red(code, out, "heartbeat killed=true after the kill")


def test_FAULT_a_revive_that_answers_200_and_leaves_the_canary_killed_is_red(estate):
    _arm(estate, "enforce")
    estate.fault("revive_leaves_killed")
    code, out = run(estate, keyed=True)
    assert code == 3, out                      # left killed: distinct from a plain failed check
    assert any("heartbeat killed=false after the revive" in ln for ln in failed(out))
    assert "CANARY STILL KILLED" in out and "--restore" in out
    assert canary_killed(estate)


def test_FAULT_the_ledger_being_unreadable_is_a_fail_never_a_pass(estate):
    _arm(estate, "log-only")
    estate.fault("ledger_events_500")
    code, out = run(estate)
    assert code == 1, out
    assert failed(out)


def test_the_redactor_scrubs_key_hash_and_secret_from_anything_the_tool_prints(estate, monkeypatch):
    """Last line of defence: even if a future edit prints a secret, it never reaches the terminal."""
    def noisy(args, secret, key):
        print("key", key)
        print("hash", hashlib.sha256(key.encode()).hexdigest())
        print("secret", secret)
        print("fp", hashlib.sha256(key.encode()).hexdigest()[:8], file=sys.stderr)
        return 0
    monkeypatch.setattr(phase_g_check, "_run", noisy)
    code, out = run(estate, keyed=True)
    assert code == 0
    assert_secret_free(out)
    assert out.count("<redacted>") >= 4


# --- review round: a canary the tool may have killed is never silently left killed -------------------


def test_a_kill_applied_but_answered_503_is_revived_and_reported(estate):
    _arm(estate, "enforce")
    estate.fault("kill_503_after_apply")
    code, out = run(estate, keyed=True)
    assert "CANARY MAY STILL BE KILLED" in out and "--restore" in out
    # the whole MED-1 instruction (the generic trailing NOTE also says --restore)
    assert ("  CANARY MAY STILL BE KILLED: the kill's outcome is unknown. Run --restore "
            "(attempting an emergency revive now).\n") in out, out
    assert "kill with your credentials => 200 status=killed (got HTTP 503)" in out
    assert not canary_killed(estate), out          # the emergency revive ran
    assert code == 1, out                          # the failed kill is a failed check, not "left killed"


def test_a_kill_applied_and_the_revive_also_fails_exits_3_with_the_instruction(estate):
    _arm(estate, "enforce")
    estate.fault("revive_503")
    code, out = run(estate, keyed=True)
    assert code == 3, out
    for want in ("CANARY STILL KILLED", "--restore", "restart canary-agent", "exit status 3"):
        assert want in out, want
    assert canary_killed(estate)
    assert_secret_free(out)
    # and --restore (once the revive path works again) brings it back
    estate.fault()
    code, out = run(estate, "--restore", keyed=True)
    assert code == 0 and not canary_killed(estate), out


def test_ctrl_c_during_the_kill_revives_and_gives_no_traceback(estate, monkeypatch):
    _arm(estate, "enforce")
    real_kill = phase_g_check.Ctx.kill

    def kill_then_interrupt(self, headers):
        real_kill(self, headers)                   # the server applied it ...
        raise KeyboardInterrupt                    # ... and the operator pressed Ctrl-C
    monkeypatch.setattr(phase_g_check.Ctx, "kill", kill_then_interrupt)
    code, out = run(estate, keyed=True)
    assert code == phase_g_check.EXIT_INTERRUPTED, out
    assert "interrupted (Ctrl-C)" in out and "Traceback" not in out
    assert not canary_killed(estate), "the canary was left killed"
    assert_secret_free(out)


def test_ctrl_c_during_the_kill_and_a_failing_revive_exits_3_with_the_instruction(estate, monkeypatch):
    _arm(estate, "enforce")
    estate.fault("revive_503")
    real_kill = phase_g_check.Ctx.kill

    def kill_then_interrupt(self, headers):
        real_kill(self, headers)
        raise KeyboardInterrupt
    monkeypatch.setattr(phase_g_check.Ctx, "kill", kill_then_interrupt)
    code, out = run(estate, keyed=True)
    assert code == 3 and "CANARY STILL KILLED" in out and "Traceback" not in out, out


def test_a_canary_halted_while_the_probe_runs_is_never_un_killed(estate):
    _arm(estate, "enforce")
    estate.fault("kill_after_first_revive")
    revives = len(events(estate, event_type="kill.revive", agent_id=CANARY))
    code, out = run(estate)
    assert code == 2 and "no longer active" in out, out
    assert canary_killed(estate)                   # still halted: the tool stopped before another write
    assert len(events(estate, event_type="kill.revive", agent_id=CANARY)) <= revives + 1


# --- review round: weaker evidence is not accepted -------------------------------------------------


def test_a_bare_proxy_401_is_not_taken_as_enforce(estate):
    _arm(estate, "enforce")
    estate.fault("bare_401_body")
    code, out = run(estate)
    red(code, out, "HTTP 401 without the guard's body shape")
    assert "mode UNVERIFIED" in out


def test_a_bare_proxy_400_is_not_taken_as_log_only(estate):
    _arm(estate, "log-only")
    estate.fault("bare_400_body")
    code, out = run(estate)
    red(code, out, "HTTP 400 without the guard's body shape")


def test_a_bare_400_does_not_satisfy_the_malformed_header_checks(estate):
    _arm(estate, "enforce")
    estate.fault("bare_400_body")
    code, out = run(estate)
    red(code, out, "malformed: duplicate x-field-operator headers => HTTP 400 (want 400) [body is not the guard's: UNVERIFIED]")


def test_events_about_the_other_canary_are_collateral(estate):
    _arm(estate, "log-only")
    estate.fault("collateral_other_canary")
    code, out = run(estate)
    red(code, out, "bystander.touched for canary-fly")
    assert "the other canary included" in out


def test_a_powershell_bom_key_file_is_accepted(estate):
    _arm(estate, "enforce")
    bom = estate.key_file.with_name("bom.key")
    bom.write_bytes(b"\xef\xbb\xbf" + KEY_DON.encode() + b"\r\n")
    code, out = run(estate, "--expect-mode", "enforce", keyed=True, key_file=bom)
    assert code == 0, out
    junk = estate.key_file.with_name("junk.key")
    junk.write_bytes(b"\xff\xfe\x00bad")
    code, out = run(estate, "--expect-mode", "enforce", keyed=True, key_file=junk)
    assert code == 2 and "bad" not in out


def test_the_env_operator_key_over_cleartext_to_a_public_host_is_refused(est, monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR_KEY", KEY_DON)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        with pytest.raises(SystemExit) as exc:
            phase_g_check.main(["--base", "http://8.8.8.8:8080"])      # no secret, no key file
    assert exc.value.code == 2 and "cleartext" in out.getvalue()
    assert KEY_DON not in out.getvalue()


def test_a_reflected_key_in_a_body_is_never_printed_even_if_the_tool_printed_bodies(estate, monkeypatch):
    """With the REAL redactor: make the tool echo every response body it reads. The reflected key
    must come out as <redacted>, never verbatim."""
    _arm(estate, "enforce")
    estate.fault("revive_echo_headers")
    real_send = phase_g_check.Sender.send

    def noisy_send(self, method, path, body, headers):
        status, parsed, text = real_send(self, method, path, body, headers)
        print("BODY", text)
        return status, parsed, text
    monkeypatch.setattr(phase_g_check.Sender, "send", noisy_send)
    code, out = run(estate, keyed=True)
    assert code == 1
    assert "<redacted>" in out
    assert_secret_free(out)


# --- review round: one fault per remaining check, each asserting its own check's label -----------------


@pytest.mark.parametrize("mode,keyed,fault,needle", [
    ("enforce", True, "kill_report_wrong_operator", "the kill report names the authenticated operator id"),
    ("log-only", False, "logonly_refuses", "log-only: unknown operator id with a made-up key => HTTP 403 (want 200)"),
    ("off", False, "nocred_503", "no-credential guarded write answered HTTP 503"),
    ("log-only", False, "longkey_503", "over-long key header answered HTTP 503"),
    ("enforce", False, "enforce_ledgers_unauth", "enforce: the no-credential write left NO operator.unauthenticated event"),
    ("log-only", False, "full_hash_fp_event", "every non-null operator_key_fp is exactly 8 lowercase hex"),
    ("log-only", False, "ledger_forges_attribution", "allowed but NOT attributed"),
    ("log-only", False, "ledger_drops_claimed", "ledgers operator_claimed as the header said"),
    ("log-only", False, "ledger_reason_nocred_wrong", "that event says action=revive reason=no_credential"),
    ("log-only", False, "ledger_reason_badcred_wrong", "ledgered operator.unauthenticated reason=bad_credential"),
    ("enforce", True, "ledger_drops_kill_agent", "exactly +1 kill.agent for the canary"),
    ("enforce", True, "ledger_drops_kill_revive", "exactly +1 kill.revive for the canary"),
    ("enforce", True, "registry_status_hides_kill", "registry status is killed"),
    ("enforce", False, "ledger_health_500", "cannot read the ledger event count"),
])
def test_FAULT_each_remaining_check_goes_red_on_its_own_breakage(estate, mode, keyed, fault, needle):
    _arm(estate, mode)
    estate.fault(fault)
    code, out = run(estate, keyed=keyed)
    red(code, out, needle)
    assert_secret_free(out)


def test_FAULT_an_unreadable_heartbeat_fails_restore(estate):
    estate.fault("heartbeat_500")
    code, out = run(estate, "--restore")
    red(code, out, "cannot read the canary's heartbeat")


def test_FAULT_restore_that_does_not_revive_is_red(estate):
    _http("POST", f"{estate.base}/killswitch/kill/{CANARY}", {"operator": "t", "reason": "x"}, SECRET)
    _arm(estate, "enforce")
    estate.fault("revive_leaves_killed")
    code, out = run(estate, "--restore", keyed=True)
    red(code, out, "heartbeat killed=false after the revive")


def test_revive_503_names_each_failed_step(estate):
    _arm(estate, "enforce")
    estate.fault("revive_503")
    code, out = run(estate, keyed=True)
    assert code == 3
    assert any("revive with your credentials => 200 (got HTTP 503)" in ln for ln in failed(out))
    assert any("emergency revive" in ln for ln in failed(out))


# --- review round 2 -----------------------------------------------------------------------------------------


def _kill_then_crash(real_kill):
    def kill(self, headers):
        real_kill(self, headers)                   # the server applied the kill ...
        # ... then the tool hits a bug; the message carries the key, so the redactor must catch it
        raise RuntimeError(f"simulated bug after the kill {headers!r}")
    return kill


def test_an_unexpected_error_after_the_kill_revives_and_exits_1_without_a_traceback(estate, monkeypatch):
    _arm(estate, "enforce")
    monkeypatch.setattr(phase_g_check.Ctx, "kill", _kill_then_crash(phase_g_check.Ctx.kill))
    code, out = run(estate, keyed=True)
    assert code == 1, out
    assert "Traceback" not in out
    assert "error: unexpected RuntimeError: simulated bug after the kill" in out
    assert "CANARY STILL KILLED" not in out
    assert not canary_killed(estate), "the canary was left killed"
    assert_secret_free(out)


def test_an_unexpected_error_after_the_kill_with_a_failing_revive_exits_3_with_the_instruction(estate, monkeypatch):
    _arm(estate, "enforce")
    estate.fault("revive_503")
    monkeypatch.setattr(phase_g_check.Ctx, "kill", _kill_then_crash(phase_g_check.Ctx.kill))
    code, out = run(estate, keyed=True)
    assert code == 3, out
    assert "Traceback" not in out
    assert "error: unexpected RuntimeError: simulated bug after the kill" in out
    for want in ("CANARY STILL KILLED", "--restore", "exit status 3"):
        assert want in out, want
    assert canary_killed(estate)
    assert_secret_free(out)


def test_events_about_a_retired_canary_are_collateral(estate):
    _arm(estate, "log-only")
    estate.fault("collateral_retired_canary")
    code, out = run(estate)
    red(code, out, "bystander.touched for canary-gb10-retired")


def test_an_edge_that_answers_200_to_everything_is_not_taken_as_off(estate):
    estate.fault("edge_200_everything")
    code, out = run(estate)
    red(code, out, "HTTP 200 without the kill-switch's heartbeat body for the canary")
    assert "mode UNVERIFIED" in out and "inferred mode: off" not in out


def test_a_heartbeat_shaped_200_that_reaches_no_service_is_not_taken_as_off(estate):
    estate.fault("revive_200_noflip")              # the right body, but nothing behind it: no kill.revive
    code, out = run(estate)
    red(code, out, "off: the two no-credential writes left exactly two kill.revive events")
    assert "inferred mode: off" not in out


# --- review round 3 -----------------------------------------------------------------------------------------


def test_a_key_straddling_the_crash_line_bound_is_never_printed_even_in_part(estate, monkeypatch):
    """The crash line is bounded in length. The bound must come AFTER redaction: the stream redactor
    only matches a key whole, so a key cut by the bound would print its prefix."""
    _arm(estate, "enforce")
    real_kill = phase_g_check.Ctx.kill

    def kill(self, headers):
        real_kill(self, headers)
        raise RuntimeError("p" * 288 + KEY_DON + " " + hashlib.sha256(KEY_DON.encode()).hexdigest())
    monkeypatch.setattr(phase_g_check.Ctx, "kill", kill)
    code, out = run(estate, keyed=True)
    leaked = next((n for n in range(len(KEY_DON), 5, -1) if KEY_DON[:n] in out), 0)
    assert leaked == 0, f"the first {leaked} characters of the key reached the output"
    assert code == 1, out
    assert "error: unexpected RuntimeError: ppp" in out and "<redacted>" in out
    assert_secret_free(out)
    assert not canary_killed(estate)


@pytest.mark.parametrize("fault", ["ledger_revive_foreign_operator", "ledger_revive_operator_field"])
def test_off_is_not_inferred_from_kill_revive_events_that_are_not_this_tools_flags_off_writes(estate, fault):
    # real heartbeat bodies and exactly two kill.revive events: only their payloads are wrong
    estate.fault(fault)
    code, out = run(estate)
    red(code, out, "off: the two no-credential writes left exactly two kill.revive events")
    assert "inferred mode: off" not in out


# --- C-12 (guards slice): registry status changes pair with kill.* events by the same operator -----------


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_c12_every_registry_status_change_pairs_with_a_kill_event_by_the_same_operator(estate, mode):
    _arm(estate, mode)
    code, out = run(estate, "--expect-mode", mode, keyed=True)
    assert code == 0, out
    assert "6. registry status changes pair with kill.* events" in out
    assert ("registry.status_changed to killed by svc on behalf of don pairs with kill.agent "
            "by don") in out, out
    assert ("registry.status_changed to active by svc on behalf of don pairs with kill.revive "
            "by don") in out, out
    assert_secret_free(out)


def test_c12_pairing_without_a_key_has_nothing_to_pair(estate):
    _arm(estate, "enforce")
    code, out = run(estate, "--expect-mode", "enforce")
    assert code == 0, out
    assert "no registry status change of canary-gb10 since the start (nothing to pair)" in out


def test_c12_pairing_is_not_run_in_mode_off(estate):
    code, out = run(estate, "--expect-mode", "off", keyed=True)
    assert code == 0, out
    assert "mode off: status changes carry no attribution to pair - not run" in out


@pytest.mark.parametrize("mode,fault", [
    ("log-only", "ks_drops_on_behalf_of"),      # a pre-C-12 kill-switch (ENFORCE: next test)
    ("log-only", "ks_on_behalf_of_forged"),
    ("enforce", "ks_on_behalf_of_forged"),
])
def test_FAULT_c12_a_status_change_not_made_for_the_kill_event_operator_is_red(estate, mode, fault):
    """The kill-switch drops the header (a pre-C-12 kill-switch) or names someone else."""
    _arm(estate, mode)
    estate.fault(fault)
    code, out = run(estate, keyed=True)
    red(code, out, "NOT paired with a kill.* event by that operator")
    assert not canary_killed(estate)
    assert_secret_free(out)


def test_FAULT_c12_under_enforce_the_registry_refuses_a_kill_switch_that_names_nobody(estate):
    """C-12 ENFORCE refusal: the unnamed bypass-scope PATCH is 403 at the registry, so the
    kill fails (502) and the canary is never killed."""
    _arm(estate, "enforce")
    estate.fault("ks_drops_on_behalf_of")
    code, out = run(estate, keyed=True)
    red(code, out, "kill with your credentials => 200 status=killed (got HTTP 502)")
    assert not canary_killed(estate)
    assert_secret_free(out)


def test_FAULT_c12_a_direct_registry_patch_with_the_kill_switch_identity_is_red(estate):
    """RT1-3: a status PATCH sent straight to the registry with the kill-switch's own key
    (naming don) has no kill.* event of its own: it must not hide behind the tool's."""
    _arm(estate, "enforce")
    estate.fault("direct_svc_status_patch")
    code, out = run(estate, keyed=True)
    red(code, out, "NOT paired with a kill.* event by that operator")
    assert not canary_killed(estate)
    assert_secret_free(out)


# -- R2-L2: every pattern is matched WHOLE (re.fullmatch): `^...$` with .match accepts a
#    value ending in a newline, which would then be printed or compared as if well-formed.


def test_an_observer_service_value_ending_in_a_newline_prints_as_unknown(monkeypatch, capsys):
    from types import SimpleNamespace

    events = [
        {"agent_id": None, "event_type": "operator.mode_changed", "payload": {"service": "kill-switch"}},
        {"agent_id": None, "event_type": "operator.mode_changed", "payload": {"service": "agent-registry\n"}},
        {"agent_id": None, "event_type": "operator.registry_changed", "payload": {"service": "spend-governor\n"}},
    ]
    monkeypatch.setattr(phase_g_check.ep, "_ledger", lambda estate: events)
    estate_probe.RESULTS.clear()
    phase_g_check.collateral(SimpleNamespace(estate=None, agent=CANARY), 0, set())
    out = capsys.readouterr().out
    assert "1 x operator.registry_changed with no agent id (C-6 ledger observer: ?)" in out
    assert "2 x operator.mode_changed with no agent id (C-6 ledger observer: ?, kill-switch)" in out
    assert "agent-registry" not in out and "spend-governor" not in out
    estate_probe.RESULTS.clear()


@pytest.mark.parametrize("value, shown", [
    ("don", "don"), ("don\n", "(not shown)"), ("svc-killswitch\n", "(not shown)"), (None, "nobody"),
])
def test_an_operator_id_ending_in_a_newline_is_not_shown(value, shown):
    assert phase_g_check._shown(value) == shown


def test_a_key_fingerprint_ending_in_a_newline_does_not_match():
    ok, _ = phase_g_check._fields_ok({"payload": {"operator_id_authenticated": "don", "operator_claimed": "don",
                                                  "operator_key_fp": FP_DON}}, "don", FP_DON)
    assert ok
    ok, _ = phase_g_check._fields_ok({"payload": {"operator_id_authenticated": "don", "operator_claimed": "don",
                                                  "operator_key_fp": FP_DON + "\n"}}, "don", FP_DON + "\n")
    assert not ok


def test_an_operator_id_argument_ending_in_a_newline_is_refused_before_anything_is_sent(tmp_path, capsys):
    key = tmp_path / "k.key"
    key.write_text(KEY_DON)
    with pytest.raises(SystemExit) as exc:
        phase_g_check.main(["--base", "http://127.0.0.1:9", "--operator-id", "don\n", "--key-file", str(key)])
    assert exc.value.code == 2
    assert "--operator-id must match" in capsys.readouterr().err


def test_every_pattern_in_the_tool_is_matched_whole():
    """A static pin: no `_RE.match(` / `_FP.match(` call is left (a newline-tolerant `$`)."""
    import re

    src = (TOOLS / "phase_g_check.py").read_text(encoding="utf-8")
    assert not re.search(r"\b_[A-Z_]*(?:RE|FP)\.match\(", src)


# --- C-122 (reviewer R-07): the two fail-open paths ---------------------------------------------------------


def test_c122_a_run_without_expect_mode_on_an_off_estate_is_red_not_green(estate):
    """FAIL-OPEN B: the OFF estate used to pass 12/12 with 'inferred mode: off'."""
    code, out = run(estate, infer=True)
    red(code, out, "no --expect-mode given and the guard looks OFF")
    assert "NOT VERIFIED" in out and "give --expect-mode off to accept it" in out, out
    assert "inferred mode: off" in out


def test_c122_expect_mode_off_still_accepts_an_off_estate(estate):
    code, out = run(estate, "--expect-mode", "off")
    assert code == 0, out
    assert "NOT VERIFIED" not in out and "no --expect-mode given" not in out


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_c122_an_armed_mode_without_expect_mode_says_it_is_not_verified(estate, mode):
    _arm(estate, mode)
    code, out = run(estate, infer=True)
    assert f"[NOT VERIFIED] mode {mode} was only inferred from behaviour; give --expect-mode {mode} to assert it" in out, out
    assert "no --expect-mode given and the guard looks OFF" not in out
    assert f"inferred mode: {mode}" in out
    # C-287 (coordinator ruling): the checks all passed, but an unasserted armed mode is NOT a 0
    assert code == phase_g_check.EXIT_NOT_VERIFIED == 4, out
    assert not failed(out) and "checks passed" in out
    assert f"NOT VERIFIED: every check passed, but mode {mode} was only inferred from behaviour; exit status 4" in out


def test_c287_the_not_verified_exit_code_is_its_own_number():
    others = {0, 1, 2, phase_g_check.EXIT_STILL_KILLED, phase_g_check.EXIT_INTERRUPTED}
    assert phase_g_check.EXIT_NOT_VERIFIED == 4 and phase_g_check.EXIT_NOT_VERIFIED not in others


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_c287_the_same_armed_estate_with_expect_mode_exits_0(estate, mode):
    _arm(estate, mode)
    code, out = run(estate, "--expect-mode", mode)
    assert code == 0 and "NOT VERIFIED" not in out, out


def test_c287_a_failed_check_outranks_not_verified(estate):
    """Unasserted armed mode AND a red check: exit 1 (a failure), never 4."""
    _arm(estate, "enforce")
    estate.fault("ledger_status_changed_as_updated")
    code, out = run(estate, keyed=True, infer=True)
    assert code == 1, out
    assert "[NOT VERIFIED] mode enforce was only inferred" in out and "NOT VERIFIED: every check passed" not in out


def test_c287_the_exit_code_is_documented_where_an_operator_looks():
    src = (TOOLS / "phase_g_check.py").read_text(encoding="utf-8")
    assert "4 = every check passed but the armed mode" in src and "4: all checks passed but the armed mode" in src
    runbook = (TOOLS.parent / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    assert "exits **4** (EXIT_NOT_VERIFIED)" in runbook
    assert "--agent canary-fly --expect-mode log-only" in runbook


def test_c122_a_status_change_ledgered_under_another_type_fails_the_keyed_run(estate):
    """FAIL-OPEN A: the registry's status changes ledgered as registry.updated; the positive path killed and
    revived, so 'nothing to pair' proved nothing and used to exit 0 (49/49 passed)."""
    _arm(estate, "enforce")
    estate.fault("ledger_status_changed_as_updated")
    code, out = run(estate, "--expect-mode", "enforce", keyed=True)
    red(code, out, "no registry status change of canary-gb10 since the start, but the positive path killed and revived it")
    assert "want >= 2" in out, out


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_c122_a_healthy_keyed_run_records_its_two_status_changes(estate, mode):
    _arm(estate, mode)
    code, out = run(estate, "--expect-mode", mode, keyed=True)
    assert code == 0, out
    assert "the positive path's kill and revive ledgered 2 registry status change(s) of canary-gb10" in out, out


def test_c122_an_unkeyed_run_still_has_nothing_to_pair_and_passes(estate):
    _arm(estate, "enforce")
    code, out = run(estate, "--expect-mode", "enforce")
    assert code == 0, out
    assert "(nothing to pair)" in out and "the positive path's kill and revive ledgered" not in out


# --- C-340 (reviewer C-335 F-C335-2): the "left NO event" wait is load-bearing ------------------------------
# Against the local estate nothing arrives late, so no estate-backed test notices if `_no_more` stops waiting.
# These drive it directly with a fake clock: an event that lands after a few polls must be seen.


class _Clock:
    """A fake clock that cannot loop forever: a wait that stops sleeping never advances `now`, so the loop
    would spin until a timeout killed it. Past MAX_CALLS reads or sleeps it raises, and the test fails fast."""

    MAX_CALLS = 1000

    def __init__(self):
        self.now = 1000.0
        self.slept = 0.0
        self.calls = 0

    def _tick(self):
        self.calls += 1
        if self.calls > self.MAX_CALLS:
            raise AssertionError(f"the wait made more than {self.MAX_CALLS} clock calls without finishing")

    def time(self):
        self._tick()
        return self.now

    def sleep(self, s):
        self._tick()
        self.now += s
        self.slept += s


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(phase_g_check, "time", c)
    return c


def _fetch_growing(after_calls: int, base: int):
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return ["e"] * (base + (1 if calls["n"] > after_calls else 0))

    return fetch, calls


def test_no_more_sees_an_event_that_lands_after_a_few_polls(clock):
    fetch, calls = _fetch_growing(after_calls=3, base=2)
    assert len(phase_g_check._no_more(None, fetch, 2)) == 3        # a single read would say 2: "no event"
    assert calls["n"] == 4


def test_no_more_waits_the_whole_window_when_nothing_arrives(clock):
    fetch, calls = _fetch_growing(after_calls=10**9, base=2)
    assert len(phase_g_check._no_more(None, fetch, 2)) == 2
    assert clock.slept == pytest.approx(phase_g_check.SETTLE_S, abs=0.25)
    assert calls["n"] > 2


def test_no_more_window_is_the_settle_window_capped_at_three_seconds(clock, monkeypatch):
    monkeypatch.setattr(phase_g_check, "SETTLE_S", 30.0)
    fetch, _ = _fetch_growing(after_calls=10**9, base=0)
    phase_g_check._no_more(None, fetch, 0)
    assert clock.slept == pytest.approx(3.0, abs=0.25)


def test_no_more_returns_at_once_when_the_count_is_already_above(clock):
    fetch, calls = _fetch_growing(after_calls=0, base=2)           # first read already has 3 > 2
    assert len(phase_g_check._no_more(None, fetch, 2)) == 3
    assert calls["n"] == 1 and clock.slept == 0.0


def test_no_more_passes_an_unreadable_ledger_through(clock):
    assert phase_g_check._no_more(None, lambda: None, 2) is None
    assert clock.slept == 0.0
