"""The rotate-then-verify-then-revoke engine, driven against the FAKE provider.

Every property is asserted on the fake's own records (which credentials are
active, who revoked them, what the consumer holds) and on the journal's bytes,
never on the engine's say-so. Failure injection:

* ``SimulatedCrash`` (a BaseException, so no ``except Exception`` swallows it) is
  raised at every named crash point between every pair of states, then a FRESH
  Rotator over the same state directory resumes; a second crash during the resume
  is tried at every point too;
* verification failure at every crash point of the rollback path;
* a human revoking the old / the new credential at the worst moments;
* a verifier that ignores the credential, a mint that answers with another
  lifetime, an install that raises, a provider that will not confirm a revoke.
"""
from __future__ import annotations

import hashlib
import itertools
import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from deployment_agent import rotation  # noqa: E402
from deployment_agent.actions import ADR_SCOPE  # noqa: E402
from deployment_agent.journal import (  # noqa: E402
    Journal, JournalError, JournalSecretError, SecretGuard, validate_target,
)
from deployment_agent.provider import (  # noqa: E402
    ADR_POINTER, FakeProvider, Provider, RealProviderNotImplemented,
)
from deployment_agent.rotation import (  # noqa: E402
    CHECKPOINTS_HAPPY, CHECKPOINTS_ROLLBACK, FileLock, ProviderError, Rotator, SimulatedCrash, _Ctx,
)
from deployment_agent.secrets_guard import SecretValue, looks_like_secret  # noqa: E402
from deployment_agent.states import (  # noqa: E402
    HAPPY_PATH, TERMINAL, TRANSITIONS, IllegalTransition, State, check_transition,
)

T = "fly-app-a"
AGENT = "ssl-deployment-agent"


def setup(tmp_path, **kw):
    fake = FakeProvider()
    old = fake.seed(T)
    return fake, old, Rotator(fake, tmp_path / "state", **kw)


def crash_at(name):
    def fault(n):
        if n == name:
            raise SimulatedCrash(name)
    return fault


def states(rot, target=T):
    return [e["state"] for e in rot.journal(target).entries() if e.get("event") == "transition"]


def assert_consistent(fake, rot, target=T):
    """Exactly one live credential, it is the one the consumer holds, nothing is left staged."""
    active = fake.active_ids(target)
    assert len(active) == 1, f"active credentials: {active}"
    assert fake.configured[target] == active[0]
    assert fake.installed[target] == fake.secrets[active[0]].reveal().encode()
    assert list(rot.stage_dir.glob(f"{target}.*")) == []
    # the journal replays cleanly through the transition table
    prev = None
    for s in states(rot, target):
        s = State(s)
        check_transition(None if prev in TERMINAL else prev, s)
        prev = s


def assert_journal_clean(fake, rot, target=T):
    text = rot.journal(target).path.read_text(encoding="utf-8") if rot.journal(target).path.exists() else ""
    for sec in fake.minted_secrets:
        assert sec.reveal() not in text
        assert sec.reveal()[:12] not in text
    assert not re.search(r"[0-9a-f]{24,}", text), "a long hex run in the journal"
    for line in text.splitlines():
        assert not looks_like_secret(line.replace('"sha"', ""))  # only ids, prefixes, prose


# ---- the transition table ------------------------------------------------------------------------------


def test_the_eight_states_and_their_table():
    assert {s.value for s in State} == {
        "planned", "minted", "installed", "verified", "old_revoked", "done", "rolled_back", "halted"}
    assert set(TRANSITIONS) == set(State)
    assert TERMINAL == {State.DONE, State.ROLLED_BACK, State.HALTED}
    for s in TERMINAL:
        assert TRANSITIONS[s] == frozenset()


def test_happy_path_pairs_are_legal_and_every_live_state_can_halt():
    for a, b in zip(HAPPY_PATH, HAPPY_PATH[1:]):
        check_transition(a, b)
    for s in set(State) - TERMINAL:
        check_transition(s, State.HALTED)


def test_illegal_transitions_raise():
    for a, b in [
        (State.PLANNED, State.VERIFIED), (State.MINTED, State.OLD_REVOKED), (State.INSTALLED, State.DONE),
        (State.VERIFIED, State.ROLLED_BACK),  # after a pass the only way is forward or a halt
        (State.DONE, State.PLANNED), (State.ROLLED_BACK, State.MINTED), (State.HALTED, State.DONE),
        (State.OLD_REVOKED, State.INSTALLED),
    ]:
        with pytest.raises(IllegalTransition):
            check_transition(a, b)
    with pytest.raises(IllegalTransition):
        check_transition(None, State.MINTED)


def test_the_journal_enforces_the_table(tmp_path):
    j = Journal(tmp_path, T)
    with pytest.raises(IllegalTransition):
        j.transition(State.DONE, run_id="r1")
    j.transition(State.PLANNED, run_id="r1", cred_old="fk-0001")
    with pytest.raises(IllegalTransition):
        j.transition(State.VERIFIED, run_id="r1")


# ---- the happy path -------------------------------------------------------------------------------------------


def test_clean_rotation_goes_through_every_state_and_leaves_one_live_credential(tmp_path):
    fake, old, rot = setup(tmp_path)
    before = fake.read_installed(T)
    res = rot.rotate(T)
    assert (res.outcome, res.exit_code) == ("done", 0)
    assert states(rot) == [s.value for s in HAPPY_PATH]
    assert fake.creds[old].state == "revoked" and fake.creds[old].revoked_by == AGENT
    assert fake.read_installed(T) != before
    assert_consistent(fake, rot)
    assert_journal_clean(fake, rot)
    assert rot.trace == list(CHECKPOINTS_HAPPY)


def test_every_pair_of_happy_path_states_has_a_crash_point_between_them():
    between = {
        ("planned", "minted"): {"after_mint", "after_stage"},
        ("minted", "installed"): {"after_minted", "after_backup", "after_install_write"},
        ("installed", "verified"): {"after_installed", "after_verify_call"},
        ("verified", "old_revoked"): {"after_verified", "after_revoke_old"},
        ("old_revoked", "done"): {"after_old_revoked"},
    }
    assert set(between) == {(a.value, b.value) for a, b in zip(HAPPY_PATH, HAPPY_PATH[1:])}
    assert set().union(*between.values()) | {"after_planned", "after_done"} == set(CHECKPOINTS_HAPPY)


def test_the_new_secret_is_staged_0600_and_only_ever_in_the_stage_dir(tmp_path):
    fake, _, rot = setup(tmp_path, fault=crash_at("after_stage"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    staged = rot.stage_dir / f"{T}.new"
    assert staged.read_bytes() == fake.minted_secrets[-1].reveal().encode()
    if sys.platform != "win32":
        assert (staged.stat().st_mode & 0o777) == 0o600
    leaked = [p for p in tmp_path.rglob("*") if p.is_file() and fake.minted_secrets[-1].reveal().encode() in p.read_bytes()]
    assert leaked == [staged]


# ---- crash between each pair of states, then resume --------------------------------------------------------------


@pytest.mark.parametrize("point", CHECKPOINTS_HAPPY)
def test_crash_at_each_point_then_resume_completes(tmp_path, point):
    fake, old, rot = setup(tmp_path, fault=crash_at(point))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    # a fresh process over the same state directory
    rot2 = Rotator(fake, tmp_path / "state")
    if point == "after_done":
        assert states(rot2)[-1] == "done"  # finished; a crash only skipped the cleanup
        assert rot2.tidy(T)
        assert_consistent(fake, rot2)
    else:
        res = rot2.rotate(T)
        assert res.outcome == "done", (point, res)
        assert fake.creds[old].state == "revoked"
        assert states(rot2)[-1] == "done"
        assert_consistent(fake, rot2)
    assert_journal_clean(fake, rot2)
    # no credential minted by an interrupted attempt is left alive
    assert len(fake.active_ids(T)) == 1


@pytest.mark.parametrize("first", CHECKPOINTS_HAPPY[:-1])
@pytest.mark.parametrize("second", CHECKPOINTS_HAPPY[:-1])
def test_two_crashes_in_a_row_still_converge(tmp_path, first, second):
    fake, old, rot = setup(tmp_path, fault=crash_at(first))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    try:
        Rotator(fake, tmp_path / "state", fault=crash_at(second)).rotate(T)
    except SimulatedCrash:
        pass
    res = Rotator(fake, tmp_path / "state").rotate(T)
    assert res.outcome == "done"
    assert fake.creds[old].state == "revoked"
    assert_consistent(fake, Rotator(fake, tmp_path / "state"))
    assert_journal_clean(fake, rot)


def test_resume_does_not_start_over_it_continues_the_run(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_installed"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    minted_before = len(fake.minted_secrets)
    Rotator(fake, tmp_path / "state").rotate(T)
    assert len(fake.minted_secrets) == minted_before  # no second mint: it verified and revoked
    assert len({e["run_id"] for e in rot.journal(T).entries() if "run_id" in e}) == 1


def test_a_mint_that_never_reached_the_journal_is_revoked_on_resume(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_mint"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    orphan = fake.minted_secrets and [c for c in fake.active_ids(T) if c != old][0]
    Rotator(fake, tmp_path / "state").rotate(T)
    assert fake.creds[orphan].state == "revoked" and fake.creds[orphan].revoked_by == AGENT


def test_a_torn_final_journal_line_is_skipped_and_the_run_resumes(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_installed"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    with open(rot.journal(T).path, "ab") as fh:
        fh.write(b'{"event":"transition","state":"veri')  # died mid-write
    res = Rotator(fake, tmp_path / "state").rotate(T)
    assert res.outcome == "done"
    assert_consistent(fake, rot)


# ---- verification failure restores the old credential ----------------------------------------------------------


def test_verify_failure_restores_the_old_value_byte_for_byte_and_revokes_the_new(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.verify_result = False
    before = fake.read_installed(T)
    res = rot.rotate(T)
    assert (res.outcome, res.exit_code) == ("rolled_back", 1)
    assert fake.read_installed(T) == before
    assert fake.creds[old].state == "active"
    new = [c for c in fake.creds if c != old][0]
    assert fake.creds[new].state == "revoked" and fake.creds[new].revoked_by == AGENT
    assert states(rot) == ["planned", "minted", "installed", "rolled_back"]
    assert_consistent(fake, rot)
    assert_journal_clean(fake, rot)
    assert rot.trace == list(CHECKPOINTS_HAPPY[:CHECKPOINTS_HAPPY.index("after_installed") + 1]) + list(CHECKPOINTS_ROLLBACK)


@pytest.mark.parametrize("point", list(CHECKPOINTS_HAPPY[: CHECKPOINTS_HAPPY.index("after_installed") + 1]) + list(CHECKPOINTS_ROLLBACK))
def test_crash_anywhere_on_the_failure_path_still_ends_with_the_old_credential(tmp_path, point):
    fake, old, rot = setup(tmp_path, fault=crash_at(point))
    fake.verify_result = False
    before = fake.read_installed(T)
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    rot2 = Rotator(fake, tmp_path / "state")
    if point != "after_rolled_back":
        assert rot2.rotate(T).outcome == "rolled_back"
    else:
        assert rot2.tidy(T)  # the run finished; only its cleanup was skipped
    assert states(rot2)[-1] == "rolled_back"
    assert fake.creds[old].state == "active"
    assert fake.read_installed(T) == before
    assert_consistent(fake, rot2)
    assert_journal_clean(fake, rot2)


def test_a_verifier_that_ignores_the_credential_is_caught_by_the_negative_control(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.verifier_ignores_secret = True  # says yes to anything, including a bogus credential
    res = rot.rotate(T)
    assert res.outcome == "rolled_back" and "ignores the credential" in res.reason
    assert fake.creds[old].state == "active"
    assert_consistent(fake, rot)


def test_a_verifier_that_raises_is_a_failed_verification(tmp_path):
    fake, old, rot = setup(tmp_path)

    def boom():
        raise RuntimeError("provider down")
    fake.on_verify.append(boom)
    assert rot.rotate(T).outcome == "rolled_back"
    assert fake.creds[old].state == "active"
    assert_consistent(fake, rot)


def test_a_mint_with_another_lifetime_is_revoked_and_never_installed(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.mint_ttl_override = 3650
    res = rot.rotate(T)
    assert res.outcome == "rolled_back"
    assert ("install", T) not in fake.calls
    assert fake.creds[old].state == "active"
    assert_consistent(fake, rot)


def test_an_install_that_raises_rolls_back_with_the_old_value_intact(tmp_path):
    fake, old, rot = setup(tmp_path)
    before = fake.read_installed(T)
    fake.install_error = OSError("consumer unavailable")
    res = rot.rotate(T)
    assert res.outcome == "rolled_back"
    assert fake.read_installed(T) == before
    assert fake.creds[old].state == "active"


def test_a_provider_that_will_not_confirm_the_revoke_halts_with_both_credentials_live(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.revoke_noop = True
    res = rot.rotate(T)
    assert res.outcome == "halted" and "did not confirm" in res.reason
    assert fake.creds[old].state == "active"
    assert states(rot)[-1] == "halted"


# ---- a human's revocation is never undone ------------------------------------------------------------------


def test_a_credential_revoked_by_a_human_before_the_run_is_refused_and_nothing_is_minted(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.human_revoke(old)
    res = rot.rotate(T)
    assert res.outcome == "refused" and res.reason.startswith("R12")
    assert [c for c in fake.calls if c[0] in ("mint", "install", "revoke")] == []
    assert fake.creds[old].state == "revoked" and fake.creds[old].revoked_by == "human"
    assert states(rot) == []


def test_a_human_revoking_the_old_credential_mid_run_is_not_worked_around(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.on_verify.append(lambda: fake.human_revoke(old) if fake.creds[old].state == "active" else None)
    res = rot.rotate(T)
    assert res.outcome == "halted" and res.exit_code == 2
    assert fake.creds[old].revoked_by == "human"
    new = [c for c in fake.creds if c != old][0]
    assert fake.creds[new].state == "revoked"  # revoked too: the new one is not left as a substitute
    # the old value was never written back
    assert [c for c in fake.calls if c[0] == "install"] == [("install", T)]


def test_a_human_revoking_the_new_credential_mid_run_leaves_everything_as_it_is(tmp_path):
    fake, old, rot = setup(tmp_path)

    # the human's revoke lands AFTER the verifier returned success, so this is not a plain verify failure
    real_verify = fake.verify

    def verify_then_human_revokes(target, secret):
        ok = real_verify(target, secret)
        if ok:
            for c in fake.creds:
                if c != old and fake.creds[c].state == "active":
                    fake.human_revoke(c)
        return ok
    fake.verify = verify_then_human_revokes
    installed_before = len([c for c in fake.calls if c[0] == "install"])
    res = rot.rotate(T)
    new = [c for c in fake.creds if c != old][0]
    assert res.outcome == "halted"
    assert fake.creds[new].revoked_by == "human"  # stays attributed to the human
    assert fake.creds[old].state == "active"  # not revoked, not touched
    assert len([c for c in fake.calls if c[0] == "install"]) == installed_before + 1  # nothing restored
    assert (rot.stage_dir / f"{T}.old").exists()  # evidence kept for the human


def test_verification_failure_with_a_human_revoked_old_credential_does_not_restore_it(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.verify_result = False
    fake.on_verify.append(lambda: fake.human_revoke(old) if fake.creds[old].state == "active" else None)
    res = rot.rotate(T)
    assert res.outcome == "halted"
    assert fake.creds[old].state == "revoked" and fake.creds[old].revoked_by == "human"
    new = [c for c in fake.creds if c != old][0]
    assert fake.creds[new].state == "active"  # left in place: no restore, no un-revoke
    assert [c for c in fake.calls if c[0] == "install"] == [("install", T)]


def test_an_old_credential_that_expired_during_a_failed_verification_is_not_restored(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.verify_result = False
    fake.on_verify.append(lambda: fake.expire(old) if fake.creds[old].state == "active" else None)
    assert rot.rotate(T).outcome == "halted"
    assert fake.creds[old].state == "expired"


def test_a_human_revoking_the_old_credential_after_verification_is_left_revoked(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_verified"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    fake.human_revoke(old)
    res = Rotator(fake, tmp_path / "state").rotate(T)
    assert res.outcome == "done"
    assert fake.creds[old].revoked_by == "human"  # never re-attributed, never touched
    assert ("revoke", old) not in fake.calls


def test_tidy_never_touches_a_pending_or_halted_run(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_minted"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    assert Rotator(fake, tmp_path / "state").tidy(T) is False
    assert (rot.stage_dir / f"{T}.new").exists()


def test_a_halted_journal_blocks_every_run_until_a_human_clears_it(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.revoke_noop = True
    assert rot.rotate(T).outcome == "halted"
    fake.revoke_noop = False
    calls = list(fake.calls)
    again = rot.rotate(T)
    assert again.outcome == "halted" and "human must clear" in again.reason
    assert fake.calls == calls  # nothing at all happened
    with pytest.raises(JournalError):
        rot.journal(T).transition(State.PLANNED, run_id="r9")
    rot.clear_halt(T, "appr-7", orphan_revoked_ack=True)
    with pytest.raises(ValueError):
        rot.clear_halt(T, "appr-8", orphan_revoked_ack=True)  # no longer halted


# ---- preconditions: lock, kill switch, scope ---------------------------------------------------------------


def test_a_held_lock_skips_the_run_with_exit_3_and_changes_nothing(tmp_path):
    fake, old, rot = setup(tmp_path)
    with FileLock(rot.state_dir / f".{T}.rotate-lock"):
        res = rot.rotate(T)
    assert (res.outcome, res.exit_code) == ("locked", 3)
    assert fake.calls == [] and states(rot) == []
    assert rot.rotate(T).outcome == "done"  # released: runs


def test_the_lock_is_released_when_the_process_dies(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_minted"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    with FileLock(rot.state_dir / f".{T}.rotate-lock"):
        pass


def test_an_engaged_kill_switch_starts_nothing_and_resumes_nothing(tmp_path):
    fake, old, rot = setup(tmp_path, kill_check=lambda: True)
    assert rot.rotate(T).outcome == "refused"
    assert fake.calls == [] and states(rot) == []
    fake2, _, rot2 = setup(tmp_path / "b", fault=crash_at("after_minted"))
    with pytest.raises(SimulatedCrash):
        rot2.rotate(T)
    calls = list(fake2.calls)
    killed = Rotator(fake2, tmp_path / "b" / "state", kill_check=lambda: True)
    assert killed.rotate(T).outcome == "refused"
    assert fake2.calls == calls


@pytest.mark.parametrize("missing", ["mint fly deploy token", "write github env secret", "revoke fly deploy token"])
def test_a_manifest_scope_missing_any_step_refuses_before_the_first_mint(tmp_path, missing):
    fake, old, rot = setup(tmp_path, scope=frozenset(ADR_SCOPE - {missing}))
    res = rot.rotate(T)
    assert res.outcome == "refused" and res.reason.startswith("R15")
    assert fake.calls == [] and states(rot) == []


def test_a_scope_wider_than_the_adr_ceiling_is_refused_by_the_engine(tmp_path):
    fake, old, rot = setup(tmp_path, scope=frozenset(ADR_SCOPE | {"edit manifest"}))
    res = rot.rotate(T)
    assert res.outcome == "refused" and res.reason.startswith("R14")
    assert fake.calls == []


# ---- the journal never holds a secret ----------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    "fakesecret-" + "ab" * 24,
    "fo" + "1_" + "x" * 10,
    "gh" + "p_abcdef",
    "-----" + "BEGIN PRIVATE KEY-----",
    "0123456789abcdef0123456789abcdef",
    "12345678-1234-1234-1234-123456789abc",
    "sk-live",
])
def test_the_journal_refuses_anything_that_looks_like_a_secret_and_writes_nothing(tmp_path, bad):
    j = Journal(tmp_path, T)
    j.transition(State.PLANNED, run_id="r1", cred_old="fk-0001")
    before = j.path.read_bytes()
    for field in ("reason", "ref"):
        with pytest.raises(JournalSecretError):
            j.append(event="note", **{field: bad})
    with pytest.raises(JournalSecretError):
        j.append(event="note", reason="ok", snapshot=[bad])
    assert j.path.read_bytes() == before


def test_the_journal_refuses_secret_values_unknown_fields_and_registered_secrets(tmp_path):
    guard = SecretGuard()
    sec = SecretValue("Zk3pq9Lw")  # short and unremarkable on its own
    guard.add(sec)
    j = Journal(tmp_path, T, guard)
    with pytest.raises(JournalSecretError):
        j.append(event="note", reason=SecretValue("anything"))
    with pytest.raises(JournalSecretError):
        j.append(event="note", token="x")  # not an allowed field
    with pytest.raises(JournalSecretError):
        j.append(event="note", reason="value was Zk3pq9Lw today")
    with pytest.raises(JournalSecretError):
        j.append(event="note", ref="not a short id!")
    j.append(event="note", reason="plain prose is fine", sha="0123456789abcdef0123456789abcdef01234567")


def test_the_journal_is_append_only(tmp_path):
    fake, old, rot = setup(tmp_path)
    j = rot.journal(T)
    seen = b""
    for fault_point in ("after_planned", "after_minted", "after_installed", "after_verified"):
        r = Rotator(fake, tmp_path / "state", fault=crash_at(fault_point))
        try:
            r.rotate(T)
        except SimulatedCrash:
            pass
        now = j.path.read_bytes()
        assert now.startswith(seen) and len(now) > len(seen)
        seen = now


def test_targets_are_validated(tmp_path):
    for bad in ("", "../x", "A", "a b", "a" * 80, "x/y"):
        with pytest.raises(ValueError):
            validate_target(bad)
    assert validate_target("fly-app-a.prod") == "fly-app-a.prod"


def test_secret_value_never_prints():
    s = SecretValue("super-secret-value-1234567890")
    assert "super" not in repr(s) and "super" not in str(s) and "super" not in f"{s}" and "super" not in "%s" % s
    assert s.prefix() == "super-se"


# ---- the provider seam --------------------------------------------------------------------------------------------


def test_fake_provider_satisfies_the_protocol_and_the_real_one_is_a_stub_pointing_at_the_adr():
    assert isinstance(FakeProvider(), Provider)
    real = RealProviderNotImplemented()
    for name in ("current", "list_credentials", "mint", "describe", "read_installed", "install", "verify", "revoke"):
        with pytest.raises(NotImplementedError, match="ADR-0079"):
            getattr(real, name)("x")
    assert "ADR-0079" in ADR_POINTER


def test_no_module_of_the_package_imports_a_network_or_process_library():
    import ast

    banned = {"socket", "http", "urllib", "requests", "subprocess", "ssl", "ftplib", "smtplib", "asyncio", "httpx"}
    for path in (TOOLS / "deployment_agent").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module.split(".")[0]]
            assert not (set(names) & banned), f"{path.name} imports {set(names) & banned}"
    assert rotation  # imported for the side effect of the check above


# ---- review fixes: the sweep ---------------------------------------------------------------------------------------------------


def _crash_after_mint(tmp_path, point="after_mint"):
    fake, old, rot = setup(tmp_path, fault=crash_at(point))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    orphan = [c for c in fake.active_ids(T) if c != old][0]
    return fake, old, orphan


@pytest.mark.parametrize("how", ["raises", "unconfirmed"])
def test_a_failed_orphan_revoke_halts_the_run_and_keeps_the_orphan_tracked(tmp_path, how):
    fake, old, orphan = _crash_after_mint(tmp_path)
    if how == "raises":
        fake.revoke_errors = 1
    else:
        fake.revoke_noop = True
    rot2 = Rotator(fake, tmp_path / "state")
    res = rot2.rotate(T)
    assert res.outcome == "halted" and res.exit_code == 2
    assert fake.creds[orphan].state == "active"  # still live ...
    entries = rot2.journal(T).entries()
    assert any(e.get("ref") == orphan for e in entries)  # ... named in a note ...
    halted = [e for e in entries if e.get("event") == "transition" and e["state"] == "halted"][-1]
    assert halted["cred_new"] == orphan  # ... and pinned on the halted transition itself
    assert states(rot2)[-1] == "halted"
    assert [c for c in fake.calls if c[0] == "mint"] == [("mint", T)]  # no fresh mint on top of it
    again = rot2.rotate(T)
    assert again.outcome == "halted" and "human must clear" in again.reason
    assert "fo1_" not in rot2.journal(T).path.read_text(encoding="utf-8")  # the provider message never lands in the journal


def test_the_orphan_is_stamped_and_the_agents_own_orphan_is_revoked(tmp_path):
    fake, old, orphan = _crash_after_mint(tmp_path)
    assert fake.creds[orphan].label and fake.creds[orphan].label.startswith("da-")
    res = Rotator(fake, tmp_path / "state").rotate(T)
    assert res.outcome == "done"
    assert fake.creds[orphan].state == "revoked" and fake.creds[orphan].revoked_by == AGENT


def test_a_credential_a_human_minted_survives_a_resume_and_is_reported(tmp_path):
    fake, old, orphan = _crash_after_mint(tmp_path, "after_stage")
    stranger = fake.human_mint(T)
    rot2 = Rotator(fake, tmp_path / "state")
    res = rot2.rotate(T)
    assert fake.creds[stranger].state == "active" and fake.creds[stranger].revoked_by is None  # never touched
    assert fake.creds[orphan].state == "revoked" and fake.creds[orphan].revoked_by == AGENT  # own orphan swept
    assert res.outcome == "halted" and "unknown" in res.reason
    assert any(e.get("ref") == stranger for e in rot2.journal(T).entries())
    assert ("revoke", stranger) not in fake.calls


def test_a_credential_a_human_minted_between_runs_is_not_adopted_or_revoked_by_a_fresh_run(tmp_path):
    fake, old, rot = setup(tmp_path)
    stranger = fake.human_mint(T)
    assert rot.rotate(T).outcome == "done"
    assert fake.creds[stranger].state == "active" and ("revoke", stranger) not in fake.calls


# ---- review fixes: the table, R13 in the engine, verifier hardening -----------------------------------------------------------


EXPECTED = {
    "planned": {"minted", "rolled_back", "halted"},
    "minted": {"installed", "rolled_back", "halted"},
    "installed": {"verified", "rolled_back", "halted"},
    "verified": {"old_revoked", "halted"},
    "old_revoked": {"done", "halted"},
    "done": set(), "rolled_back": set(), "halted": set(),
}


def test_the_table_is_exactly_the_documented_one():
    assert {s.value: {d.value for d in dsts} for s, dsts in TRANSITIONS.items()} == EXPECTED


@pytest.mark.parametrize("src,dst", [(a, b) for a, b in itertools.product(State, State) if b.value not in EXPECTED[a.value]],
                         ids=lambda s: s.value)
def test_every_pair_not_in_the_table_raises(src, dst):
    with pytest.raises(IllegalTransition):
        check_transition(src, dst)


PATH_TO = {
    State.PLANNED: [State.PLANNED],
    State.MINTED: [State.PLANNED, State.MINTED],
    State.INSTALLED: [State.PLANNED, State.MINTED, State.INSTALLED],
    State.VERIFIED: [State.PLANNED, State.MINTED, State.INSTALLED, State.VERIFIED],
    State.OLD_REVOKED: [State.PLANNED, State.MINTED, State.INSTALLED, State.VERIFIED, State.OLD_REVOKED],
}


@pytest.mark.parametrize("src,dst", [(a, b) for a in PATH_TO for b in State if b.value not in EXPECTED[a.value]],
                         ids=lambda s: s.value)
def test_the_journal_refuses_every_illegal_pair_too(tmp_path, src, dst):
    j = Journal(tmp_path, T)
    for st in PATH_TO[src]:
        j.transition(st, run_id="r1")
    before = j.path.read_bytes()
    with pytest.raises(IllegalTransition):
        j.transition(dst, run_id="r1")
    assert j.path.read_bytes() == before


def test_the_engine_hands_r13_the_journaled_state_not_a_constant(tmp_path):
    fake, old, rot = setup(tmp_path)
    ctx = _Ctx(T, "r1", old, 30, [old], new="fk-0002")
    assert rot._revoke(ctx, old, "old", False).startswith("R13")
    assert fake.creds[old].state == "active"
    assert rot._revoke(ctx, old, "old", True) is None
    assert fake.creds[old].state == "revoked"


def test_a_verifier_that_only_checks_the_prefix_fails_the_negative_control(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.prefix_only_verifier = True
    res = rot.rotate(T)
    assert res.outcome == "rolled_back" and "ignores" in res.reason
    assert fake.creds[old].state == "active"


@pytest.mark.parametrize("answer", [1, "yes", object()])
def test_only_exactly_true_counts_as_a_passed_verification(tmp_path, answer):
    fake, old, rot = setup(tmp_path)
    fake.verify_result = answer
    assert rot.rotate(T).outcome == "rolled_back"
    assert fake.creds[old].state == "active"


def test_the_sha_field_still_gets_the_literal_secret_check(tmp_path):
    guard = SecretGuard()
    guard.add(SecretValue("0123456789abcdef0123456789abcdef01234567"))
    j = Journal(tmp_path, T, guard)
    with pytest.raises(JournalSecretError):
        j.append(event="note", sha="0123456789abcdef0123456789abcdef01234567")
    j.append(event="note", sha="f" * 40)


def test_provider_exceptions_reach_the_caller_as_type_names_only(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.describe_error = RuntimeError("bad token fo1_" + "Q" * 30)
    with pytest.raises(ProviderError) as ei:
        rot.rotate(T)
    assert "fo1_" not in str(ei.value) and "RuntimeError" in str(ei.value)
    assert ei.value.__cause__ is None and ei.value.__context__ is None


def test_revoking_the_old_credential_before_the_journal_says_verified_halts_on_r13(tmp_path):
    fake, old, rot = setup(tmp_path)
    j = rot.journal(T)
    j.transition(State.PLANNED, run_id="r1", cred_old=old, snapshot=[old], ttl_days=30)
    j.transition(State.MINTED, run_id="r1", cred_old=old, cred_new="fk-0002")
    j.transition(State.INSTALLED, run_id="r1", cred_old=old, cred_new="fk-0002")
    ctx = _Ctx(T, "r1", old, 30, [old], new="fk-0002")
    assert rot._do_revoke_old(j, ctx) is State.HALTED
    assert ctx.reason.count("R13") == 1
    assert fake.creds[old].state == "active" and ("revoke", old) not in fake.calls


# ---- second review: the halt is always recorded --------------------------------------------------------------------------------

LONG_NAME = type("SSLCertVerificationErrorXXXXXX", (Exception,), {})  # a 30-character exception type name
assert len(LONG_NAME.__name__) == 30
PROVIDER_METHODS = ("current", "list_credentials", "mint", "describe", "read_installed", "install", "verify", "revoke")


class Exploding:
    """A FakeProvider whose chosen methods raise an exception with a 30-character type name and a secret-shaped message."""

    def __init__(self, fake, methods):
        self._fake, self._methods = fake, set(methods)

    def __getattr__(self, name):
        fn = getattr(self._fake, name)
        if name in self._methods:
            def boom(*a, **k):
                raise LONG_NAME("token fo1_" + "R" * 30)
            return boom
        return fn


def halted_entries(rot, target=T):
    return [e for e in rot.journal(target).entries() if e.get("event") == "transition" and e["state"] == "halted"]


def test_provider_error_carries_a_short_sanitised_type_token():
    fake, old = FakeProvider(), None
    err = None
    from deployment_agent.rotation import _type_token

    assert len(_type_token(LONG_NAME("x"))) <= 20
    odd = type("weird name!!with-chars" + "z" * 40, (Exception,), {})
    tok = _type_token(odd("x"))
    assert re.fullmatch(r"[A-Za-z0-9_.]{1,20}", tok), tok
    assert not looks_like_secret("provider revoke failed: " + tok)


@pytest.mark.parametrize("method", PROVIDER_METHODS)
def test_a_provider_exception_with_a_30_char_type_name_never_escapes_as_a_journal_error(tmp_path, method):
    fake = FakeProvider()
    old = fake.seed(T)
    rot = Rotator(Exploding(fake, [method]), tmp_path / "state")
    try:
        res = rot.rotate(T)
    except ProviderError as exc:
        assert "fo1_" not in str(exc) and len(str(exc)) < 80
    else:
        assert res.outcome in ("done", "rolled_back", "halted")
    assert "fo1_" not in rot.journal(T).path.read_text(encoding="utf-8") if rot.journal(T).path.exists() else True


@pytest.mark.parametrize("method", ["revoke", "describe", "list_credentials"])
def test_a_failing_sweep_with_a_30_char_exception_name_records_a_halt(tmp_path, method):
    fake, old, orphan = _crash_after_mint(tmp_path)
    rot2 = Rotator(Exploding(fake, [method]), tmp_path / "state")
    res = rot2.rotate(T)
    assert res.outcome == "halted"
    h = halted_entries(rot2)
    assert h and states(rot2)[-1] == "halted"
    assert "fo1_" not in rot2.journal(T).path.read_text(encoding="utf-8")


@pytest.mark.parametrize("method", ["revoke", "describe"])
def test_a_failing_revoke_of_the_old_credential_with_a_30_char_name_records_a_halt(tmp_path, method):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_verified"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    rot2 = Rotator(Exploding(fake, [method]), tmp_path / "state")
    res = rot2.rotate(T)
    assert res.outcome == "halted" and halted_entries(rot2)


def test_halt_falls_back_to_a_fixed_reason_when_the_journal_refuses_the_reason(tmp_path):
    from deployment_agent.rotation import FALLBACK_HALT_REASON

    fake, old, rot = setup(tmp_path)
    j = rot.journal(T)
    j.transition(State.PLANNED, run_id="r1", cred_old=old, snapshot=[old], ttl_days=30)
    ctx = _Ctx(T, "r1", old, 30, [old])
    assert rot._halt(j, ctx, "provider revoke failed: " + "A" * 40) is State.HALTED
    last = halted_entries(rot)[-1]
    assert last["reason"] == FALLBACK_HALT_REASON and ctx.reason == FALLBACK_HALT_REASON


# ---- second review: ids that are not short handles ------------------------------------------------------------------------

LONG_ID = "12345678-1234-1234-1234-{n:012d}"


def test_a_uuid_style_unknown_credential_is_journaled_by_a_safe_handle_and_the_halt_is_written(tmp_path):
    fake, old, orphan = _crash_after_mint(tmp_path, "after_stage")
    fake.id_format = LONG_ID
    stranger = fake.human_mint(T)
    assert len(stranger) == 36
    rot2 = Rotator(fake, tmp_path / "state")
    res = rot2.rotate(T)  # must not raise JournalSecretError
    assert res.outcome == "halted"
    text = rot2.journal(T).path.read_text(encoding="utf-8")
    assert stranger not in text and stranger[:8] not in text
    refs = [e["ref"] for e in rot2.journal(T).entries() if e.get("ref")]
    assert any(r.startswith("id-") and len(r) == 11 for r in refs)
    assert fake.creds[stranger].state == "active"
    assert rot2.rotate(T).outcome == "halted"  # reruns do not raise either


# (a UUID-style id on the agent's own mint is now rejected at the mint; see the third-review tests)


# ---- second review: clear_halt verifies --------------------------------------------------------------------------------------


def _halted_with_live_orphan(tmp_path):
    fake, old, orphan = _crash_after_mint(tmp_path)
    fake.revoke_errors = 1
    rot2 = Rotator(fake, tmp_path / "state")
    assert rot2.rotate(T).outcome == "halted"
    return fake, old, orphan, rot2


def test_clear_halt_requires_an_explicit_acknowledgement(tmp_path):
    fake, old, orphan, rot2 = _halted_with_live_orphan(tmp_path)
    for ack in (False, None, "yes", 1):
        with pytest.raises(ValueError):
            rot2.clear_halt(T, "appr-1", orphan_revoked_ack=ack)
    with pytest.raises(ValueError):
        rot2.clear_halt(T, "appr-1")
    assert rot2.journal(T).is_halted()


def test_clear_halt_refuses_while_the_named_orphan_is_still_live_and_clears_once_it_is_revoked(tmp_path):
    fake, old, orphan, rot2 = _halted_with_live_orphan(tmp_path)
    with pytest.raises(ValueError, match="still live"):
        rot2.clear_halt(T, "appr-1", orphan_revoked_ack=True)
    assert rot2.journal(T).is_halted()
    fake.revoke(orphan, "human")  # the human revokes it at the provider
    rot2.clear_halt(T, "appr-1", orphan_revoked_ack=True)
    assert not rot2.journal(T).is_halted()
    assert Rotator(fake, tmp_path / "state").rotate(T).outcome == "done"
    assert_consistent(fake, rot2)


def test_a_human_credential_does_not_block_clear_halt_and_joins_the_next_snapshot(tmp_path):
    fake, old, orphan = _crash_after_mint(tmp_path, "after_stage")
    stranger = fake.human_mint(T)
    rot2 = Rotator(fake, tmp_path / "state")
    assert rot2.rotate(T).outcome == "halted"
    rot2.clear_halt(T, "appr-2", orphan_revoked_ack=True)  # keeping the stranger is the human's decision
    assert Rotator(fake, tmp_path / "state").rotate(T).outcome == "done"
    assert fake.creds[stranger].state == "active"
    planned = [e for e in rot2.journal(T).entries() if e.get("event") == "transition" and e["state"] == "planned"][-1]
    assert stranger in planned["snapshot"]


# ---- second review: the stamp compare is exact, and labels must be stored -----------------------------------------------------


def _run_stamp(rot):
    planned = [e for e in rot.journal(T).entries() if e.get("event") == "transition" and e["state"] == "planned"][-1]
    return "da-" + planned["run_id"]


@pytest.mark.parametrize("variant", [
    lambda st: "da-rdeadbeef",  # another run's stamp
    lambda st: st.upper(),
    lambda st: " " + st,
    lambda st: st + " ",
    lambda st: st + "\u00a0",
    lambda st: "\u00a0" + st,
    lambda st: st + "\n",
    lambda st: st[:-1],
], ids=["other-run", "upper", "lead-space", "trail-space", "trail-nbsp", "lead-nbsp", "newline", "truncated"])
def test_only_the_exact_stamp_is_swept_every_variant_is_unknown_and_halts(tmp_path, variant):
    fake, old, orphan = _crash_after_mint(tmp_path, "after_stage")
    rot_probe = Rotator(fake, tmp_path / "state")
    stranger = fake.human_mint(T, label=variant(_run_stamp(rot_probe)))
    res = rot_probe.rotate(T)
    assert res.outcome == "halted" and "unknown" in res.reason
    assert fake.creds[stranger].state == "active" and fake.creds[stranger].revoked_by is None
    assert ("revoke", stranger) not in fake.calls
    assert fake.creds[orphan].state == "revoked"  # the exact-stamp orphan was still swept


def test_a_provider_that_drops_labels_rolls_a_normal_rotation_back(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.drop_labels = True
    res = rot.rotate(T)
    assert res.outcome == "rolled_back" and "differs" in res.reason
    assert ("install", T) not in fake.calls
    assert fake.creds[old].state == "active"
    assert_consistent(fake, rot)


def test_a_provider_that_drops_labels_makes_the_own_orphan_unknown_after_a_crash(tmp_path):
    fake = FakeProvider()
    old = fake.seed(T)
    fake.drop_labels = True
    rot = Rotator(fake, tmp_path / "state", fault=crash_at("after_mint"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    orphan = [c for c in fake.active_ids(T) if c != old][0]
    res = Rotator(fake, tmp_path / "state").rotate(T)
    assert res.outcome == "halted" and fake.creds[orphan].state == "active"


# ---- second review: `is True` on the REAL-credential check, independent of the control ----------------------------------------


@pytest.mark.parametrize("answer", [1, "yes", object(), [0]])
def test_a_truthy_non_true_answer_for_the_real_credential_fails_closed_though_the_control_passed(tmp_path, answer):
    fake, old, rot = setup(tmp_path)
    fake.real_answer = answer  # the bogus control still gets False from the fake
    res = rot.rotate(T)
    assert res.outcome == "rolled_back" and "ignores" not in res.reason  # it is the real check that refused
    assert fake.creds[old].state == "active"
    assert_consistent(fake, rot)


def test_exactly_true_for_the_real_credential_passes(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.real_answer = True
    assert rot.rotate(T).outcome == "done"


@pytest.mark.parametrize("ack", [False, None, "yes", 1])
def test_the_acknowledgement_is_required_even_when_nothing_is_live(tmp_path, ack):
    fake, old, rot = setup(tmp_path)
    fake.revoke_noop = True
    assert rot.rotate(T).outcome == "halted"  # no orphan anywhere: only the acknowledgement can refuse
    with pytest.raises(ValueError, match="orphan_revoked_ack"):
        rot.clear_halt(T, "appr-1", orphan_revoked_ack=ack)
    assert rot.journal(T).is_halted()
    rot.clear_halt(T, "appr-1", orphan_revoked_ack=True)


# ---- third review: clear_halt checks the halted row's cred_new, data-driven -------------------------------------------------

def _clear_ok_after_revoking(rot, fake, new, ack=True):
    with pytest.raises(ValueError, match="still live"):
        rot.clear_halt(T, "appr-1", orphan_revoked_ack=ack)
    assert rot.journal(T).is_halted()
    fake.revoke_errors, fake.revoke_noop = 0, False
    fake.revoke(new, "human")
    rot.clear_halt(T, "appr-1", orphan_revoked_ack=ack)
    assert not rot.journal(T).is_halted()


def _last_halt(rot):
    return halted_entries(rot)[-1]


def _new_id(fake, old):
    return [c for c in fake.creds if c != old and fake.creds[c].label][-1]


def scen_rollback_revoke_unconfirmed(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.verify_result = False
    fake.revoke_noop = True
    assert rot.rotate(T).outcome == "halted"
    return fake, old, rot


def scen_mint_mismatch_revoke_fails(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.mint_ttl_override = 3650
    fake.revoke_errors = 5
    assert rot.rotate(T).outcome == "halted"
    return fake, old, rot


def scen_install_staged_missing(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_minted"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    (rot.stage_dir / f"{T}.new").unlink()
    fake.revoke_errors = 5
    rot2 = Rotator(fake, tmp_path / "state")
    assert rot2.rotate(T).outcome == "halted"
    return fake, old, rot2


def scen_verify_staged_missing(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_installed"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    (rot.stage_dir / f"{T}.new").unlink()
    rot2 = Rotator(fake, tmp_path / "state")
    assert rot2.rotate(T).outcome == "halted"
    return fake, old, rot2


def scen_rollback_backup_missing(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_installed"))
    fake.verify_result = False
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    (rot.stage_dir / f"{T}.old").unlink()
    rot2 = Rotator(fake, tmp_path / "state")
    assert rot2.rotate(T).outcome == "halted"
    return fake, old, rot2


def scen_rollback_restore_fails(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.verify_result = False
    fake.on_verify.append(lambda: setattr(fake, "install_error", OSError("consumer down")))
    assert rot.rotate(T).outcome == "halted"
    fake.install_error = None
    return fake, old, rot


def scen_old_revoked_by_human_during_verify(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.on_verify.append(lambda: fake.human_revoke(old) if fake.creds[old].state == "active" else None)
    fake.revoke_errors = 5  # the agent's own revoke of the new credential fails too
    assert rot.rotate(T).outcome == "halted"
    return fake, old, rot


MUST_BE_REVOKED = [scen_rollback_revoke_unconfirmed, scen_mint_mismatch_revoke_fails, scen_install_staged_missing,
                   scen_verify_staged_missing, scen_rollback_backup_missing, scen_rollback_restore_fails,
                   scen_old_revoked_by_human_during_verify]


@pytest.mark.parametrize("scen", MUST_BE_REVOKED, ids=lambda f: f.__name__)
def test_clear_halt_refuses_while_the_halted_rows_new_credential_is_live(tmp_path, scen):
    fake, old, rot = scen(tmp_path)
    new = _new_id(fake, old)
    assert fake.creds[new].state == "active"
    row = _last_halt(rot)
    assert row["leaves_new_in_place"] is False and row["cred_new"] == new
    _clear_ok_after_revoking(rot, fake, new)


def scen_old_invalid_new_left_in_place(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.verify_result = False
    fake.on_verify.append(lambda: fake.human_revoke(old) if fake.creds[old].state == "active" else None)
    assert rot.rotate(T).outcome == "halted"
    return fake, old, rot


def scen_revoke_old_unconfirmed(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.revoke_noop = True
    assert rot.rotate(T).outcome == "halted"
    return fake, old, rot


def scen_new_revoked_by_someone_else(tmp_path):
    fake, old, rot = setup(tmp_path)
    real = fake.verify

    def verify_then_human_revokes(target, secret):
        ok = real(target, secret)
        if ok:
            for c in fake.creds:
                if c != old and fake.creds[c].state == "active":
                    fake.human_revoke(c)
        return ok
    fake.verify = verify_then_human_revokes
    assert rot.rotate(T).outcome == "halted"
    return fake, old, rot


LEAVES_NEW = [scen_old_invalid_new_left_in_place, scen_revoke_old_unconfirmed, scen_new_revoked_by_someone_else]


@pytest.mark.parametrize("scen", LEAVES_NEW, ids=lambda f: f.__name__)
def test_halts_that_deliberately_leave_the_new_credential_do_not_block_clear_halt(tmp_path, scen):
    fake, old, rot = scen(tmp_path)
    new = _new_id(fake, old)
    assert _last_halt(rot)["leaves_new_in_place"] is True
    if scen is not scen_new_revoked_by_someone_else:
        assert fake.creds[new].state == "active"
    rot.clear_halt(T, "appr-1", orphan_revoked_ack=True)
    assert not rot.journal(T).is_halted()


def test_every_halted_row_carries_the_flag(tmp_path):
    for i, scen in enumerate(MUST_BE_REVOKED + LEAVES_NEW):
        fake, old, rot = scen(tmp_path / str(i))
        assert isinstance(_last_halt(rot)["leaves_new_in_place"], bool)


def test_the_hashed_handle_is_findable_by_sha256_of_the_provider_id(tmp_path):
    fake, old, rot = setup(tmp_path)
    lid = "12345678-1234-1234-1234-123456789abc"
    assert rot._ref(lid) == "id-" + hashlib.sha256(lid.encode()).hexdigest()[:8]
    assert rot._ref("fk-0001") == "fk-0001"


# ---- third review: an unsafe minted id is rejected at once; a hashed cred_new is never used as an id -------------------------


def test_a_minted_id_that_is_not_a_safe_handle_is_revoked_and_halts_before_minted_is_journaled(tmp_path):
    fake = FakeProvider()
    old = fake.seed(T)
    fake.id_format = "12345678-1234-1234-1234-{n:012d}"
    rot = Rotator(fake, tmp_path / "state")
    res = rot.rotate(T)
    assert res.outcome == "halted" and "safe handle" in res.reason
    new = [c for c in fake.creds if c != old][0]
    assert len(new) == 36 and fake.creds[new].state == "revoked" and fake.creds[new].revoked_by == AGENT
    assert "minted" not in states(rot)
    row = _last_halt(rot)
    assert row["cred_new"] == rot._ref(new) and new not in rot.journal(T).path.read_text(encoding="utf-8")
    assert ("install", T) not in fake.calls
    assert rot.rotate(T).outcome == "halted"  # blocked, never raises


def test_an_unsafe_minted_id_that_cannot_be_revoked_stays_tracked_by_its_hash(tmp_path):
    fake = FakeProvider()
    old = fake.seed(T)
    fake.id_format = "12345678-1234-1234-1234-{n:012d}"
    fake.revoke_errors = 5
    rot = Rotator(fake, tmp_path / "state")
    assert rot.rotate(T).outcome == "halted"
    new = [c for c in fake.creds if c != old][0]
    assert fake.creds[new].state == "active" and _last_halt(rot)["cred_new"] == rot._ref(new)
    with pytest.raises(ValueError, match="still live"):
        rot.clear_halt(T, "appr-1", orphan_revoked_ack=True)


def test_resume_refuses_and_halts_on_a_hashed_cred_new_instead_of_calling_describe_on_it(tmp_path):
    fake, old, rot = setup(tmp_path, fault=crash_at("after_installed"))
    with pytest.raises(SimulatedCrash):
        rot.rotate(T)
    path = rot.journal(T).path
    text = path.read_text(encoding="utf-8")
    assert '"cred_new":"fk-0002"' in text
    path.write_text(text.replace('"cred_new":"fk-0002"', '"cred_new":"id-1a2b3c4d"'), encoding="utf-8")
    rot2 = Rotator(fake, tmp_path / "state")
    res = rot2.rotate(T)  # must not raise ProviderError from describe('id-1a2b3c4d')
    assert res.outcome == "halted" and "hashed" in res.reason
    assert states(rot2)[-1] == "halted" and rot2.rotate(T).outcome == "halted"


# ---- third review: unwrapped provider-call sites --------------------------------------------------------------------------------


def _boom():
    raise RuntimeError("bad token fo1_" + "Q" * 30)


def test_a_describe_that_fails_right_after_the_mint_ends_in_a_recorded_halt(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.after_mint.append(lambda: setattr(fake, "describe_error", RuntimeError("fo1_" + "Q" * 30)))
    res = rot.rotate(T)
    assert res.outcome == "halted" and halted_entries(rot)
    assert fake.creds[_new_id(fake, old)].state == "active"  # still live and tracked
    assert "fo1_" not in rot.journal(T).path.read_text(encoding="utf-8")


def test_a_describe_that_returns_garbage_right_after_the_mint_ends_in_a_recorded_halt(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.after_mint.append(lambda: setattr(fake, "describe_result", None))
    res = rot.rotate(T)
    assert res.outcome == "halted" and halted_entries(rot)


def test_describes_that_fail_after_a_passed_verification_end_in_a_recorded_halt(tmp_path):
    fake, old, rot = setup(tmp_path)
    calls = []

    def hook():
        calls.append(1)
        if len(calls) == 2:  # the real-credential check: from here every describe raises
            fake.describe_error = RuntimeError("fo1_" + "Q" * 30)
    fake.on_verify.append(hook)
    res = rot.rotate(T)
    assert res.outcome == "halted" and halted_entries(rot) and states(rot)[-1] == "halted"


def test_a_describe_that_fails_at_the_start_of_a_rollback_ends_in_a_recorded_halt(tmp_path):
    fake, old, rot = setup(tmp_path)
    fake.verify_result = False
    fake.on_verify.append(lambda: setattr(fake, "describe_error", RuntimeError("fo1_" + "Q" * 30)))
    res = rot.rotate(T)
    assert res.outcome == "halted" and halted_entries(rot)


def test_a_read_installed_that_fails_before_the_backup_rolls_back_without_touching_the_consumer(tmp_path):
    fake, old, rot = setup(tmp_path)
    before = fake.installed[T]
    fake.read_installed_error = RuntimeError("fo1_" + "Q" * 30)
    res = rot.rotate(T)
    assert res.outcome == "rolled_back"
    assert fake.installed[T] == before and ("install", T) not in fake.calls
    assert fake.creds[old].state == "active"


def test_garbage_from_any_provider_method_becomes_a_provider_error_not_an_attribute_error(tmp_path):
    class Garbage:
        def __init__(self, fake, name):
            self._f, self._n = fake, name

        def __getattr__(self, name):
            if name == self._n:
                return lambda *a, **k: object()
            return getattr(self._f, name)
    for method in ("current", "list_credentials", "describe", "read_installed", "mint"):
        fake = FakeProvider()
        fake.seed(T)
        rot = Rotator(Garbage(fake, method), tmp_path / method)
        try:
            res = rot.rotate(T)
        except ProviderError as exc:
            assert "BadResponse" in str(exc)
        else:
            assert res.outcome in ("done", "rolled_back", "halted")


def test_an_exception_whose_metaclass_name_raises_never_escapes_or_carries_text(tmp_path):
    class Meta(type):
        @property
        def __name__(cls):
            raise RuntimeError("fo1_" + "Q" * 30)
    Evil = Meta("Evil", (Exception,), {})
    for bad in (Evil("fo1_" + "Q" * 30),):
        fake = FakeProvider()
        fake.seed(T)
        fake.describe_error = bad
        rot = Rotator(fake, tmp_path / "s")
        with pytest.raises(ProviderError) as ei:
            rot.rotate(T)
        assert "fo1_" not in str(ei.value) and ei.value.__context__ is None and ei.value.__cause__ is None
    from deployment_agent.rotation import _type_token

    assert _type_token(Evil("x")) == "Error"
    class Meta2(type):
        @property
        def __name__(cls):
            return 7
    assert _type_token(Meta2("N", (Exception,), {})("x")) == "Error"


def test_a_journal_write_that_fails_while_halting_raises_fixed_text_with_no_path(tmp_path, monkeypatch):
    from deployment_agent.rotation import HaltWriteError

    fake, old, rot = setup(tmp_path)
    fake.revoke_noop = True
    real = Journal.transition

    def failing(self, state, **fields):
        if state is State.HALTED:
            raise OSError(28, r"C:\very\secret\path no space left")
        return real(self, state, **fields)
    monkeypatch.setattr(Journal, "transition", failing)
    with pytest.raises(HaltWriteError) as ei:
        rot.rotate(T)
    assert "secret" not in str(ei.value) and "path" not in str(ei.value)
    assert ei.value.__context__ is None and ei.value.__cause__ is None
    monkeypatch.undo()
    assert states(rot)[-1] == "verified"  # the journal kept its prior state; the next run resumes
    assert fake.creds[old].state == "active"
    fake.revoke_noop = False
    assert Rotator(fake, tmp_path / "state").rotate(T).outcome == "done"
