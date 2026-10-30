"""Key rotation slice R4a, rework after the CONDITIONS review (PR #57, head
09dcbcd: C-1 condition 1, C-16 findings 1 and 2, C-17's 50 surviving mutants
on ``rotation.py``). Every test here pins a guard the earlier tests left
unexercised (crash-recovery and precondition branches), or a behaviour added
in this rework: the post-PROMOTE retry cap, the ledgered migration crash and
the lost status file. Every key is a fake test value made in a temp
directory."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rotation_fakes_r4a import T0, Bed, Crash, ROTATOR_ID, sha  # noqa: E402

from field_core import operator_auth as oa  # noqa: E402
from field_core import rotation as rot  # noqa: E402

KS = "svc-killswitch"
REG = "svc-registry"


@pytest.fixture(autouse=True)
def _fresh_memory(monkeypatch):
    oa.reset_retired_memory()
    if os.name == "nt":
        monkeypatch.setattr(rot.os, "fsync", lambda fd: None)
    yield
    oa.reset_retired_memory()


@pytest.fixture
def bed(tmp_path):
    return Bed(tmp_path)


def _crash_at(bed, point, oid=KS, **kw):
    """Run until the first ``point``, then die; returns the identity."""
    seen = {"n": 0}

    def hook(p):
        if p == point:
            seen["n"] += 1
            if seen["n"] == 1:
                raise Crash()
    with pytest.raises(Crash):
        bed.rotator(hook=hook, **kw).run_once(now_id=oid)
    return bed.identity(oid)


def _journal(bed, oid=KS) -> rot.Journal:
    return rot.Journal.from_bytes((bed.state / f"journal-{oid}.json").read_bytes())


def _stalled(bed, point, phase=None, oid=KS):
    """(rotator, journal, identity) of a rotation that died at ``point``,
    optionally with the journal moved to ``phase``."""
    identity = _crash_at(bed, point, oid)
    r = bed.rotator()
    j = _journal(bed, oid)
    if phase is not None:
        j.phase = phase
    return r, j, identity


def _files(bed):
    return sorted(str(p.relative_to(bed.root)) for p in bed.root.rglob("*")
                  if p.name != rot.LOCK_NAME)


def _write_doc(bed, doc):
    bed.ops.write_bytes(rot.encode_doc(doc))


# ---------------------------------------------------------------------------
# condition 1: the TOCTOU between the start check and PROMOTE
# ---------------------------------------------------------------------------

def test_a_next_slot_edited_between_the_start_check_and_promote_is_a_foreign_edit(bed):
    done = {"n": 0}

    def hook(point):
        if point == "after_switch" and not done["n"]:
            done["n"] = 1
            doc = bed.live()
            row = next(r for r in doc["operators"] if r["operator_id"] == KS)
            row["next_key"] = {**row["next_key"], "key_sha256": sha("fok_someone-elses-key")}
            _write_doc(bed, doc)
    code, summary = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "foreign_edit", summary
    assert summary["phase"] == "promote" and summary["reverted"] is False
    assert bed.estate.of("keyrotation.retired") == []
    row = bed.row(KS)
    assert row["next_key"]["key_sha256"] == sha("fok_someone-elses-key")   # the edit is kept
    assert row["key_sha256"] != bed.key_sha(KS)                            # nothing promoted


# ---------------------------------------------------------------------------
# _abort: nothing is rolled back after PROMOTE (C-17 L911)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase", ["promote", "verify_current", "confirm_refused"])
def test_abort_after_promote_restores_nothing(bed, phase):
    r, j, identity = _stalled(bed, "after_switch", phase)
    kp = Path(identity.key_path)
    new_sha, ops = bed.key_sha(KS), bed.ops.read_bytes()
    with pytest.raises(rot._Stop) as ei:
        raise r._abort(j, identity, "soak", "refusal_seen")
    assert ei.value.summary["result"] == "failed"
    assert bed.key_sha(KS) == new_sha and Path(str(kp) + ".prev").exists()   # no key restore
    assert bed.ops.read_bytes() == ops                                       # no next_key edit
    assert bed.estate.of("keyrotation.aborted") == []
    assert (bed.state / f"journal-{KS}.json").exists()


# ---------------------------------------------------------------------------
# _precheck on the --now path (C-17 L1181): _choose is skipped there
# ---------------------------------------------------------------------------

def _edit_row(bed, **changes):
    doc = bed.live()
    row = next(r for r in doc["operators"] if r["operator_id"] == KS)
    row.update(changes)
    _write_doc(bed, doc)


@pytest.mark.parametrize("what", ["revoked", "remote", "has_next_key"])
def test_now_on_a_row_that_is_not_active_auto_without_next_key_is_skipped(bed, what):
    if what == "revoked":
        _edit_row(bed, status="revoked")
    elif what == "remote":
        _edit_row(bed, rotation="remote")
    else:
        _edit_row(bed, next_key={"key_sha256": sha("fok_pending"),
                                 "not_before": oa.format_time(T0 - 60),
                                 "not_after": oa.format_time(T0 + 86400)})
    oa.parse_registry_doc(bed.live(), require_active=True)           # the file itself is valid
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_SKIPPED and summary["skip_reason"] == "precheck", summary
    assert bed.ops.read_bytes() == before and not list(bed.state.glob("journal-*"))


# ---------------------------------------------------------------------------
# _soak: the daemon stops showing the new key (C-17 L1521)
# ---------------------------------------------------------------------------

def test_the_daemon_fingerprint_moving_away_during_soak_aborts(bed):
    real_sleep = bed.estate.sleep

    def sleep(seconds):
        real_sleep(seconds)
        bed.estate.services["kill-switch"].stuck_fp = "0" * 16
    bed.estate.sleep = sleep
    old = bed.key_sha(KS)
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["result"] == "aborted", summary
    assert summary["reason_class"] == "switch_not_seen" and summary["phase"] == "soak"
    assert bed.key_sha(KS) == old and bed.estate.of("keyrotation.retired") == []


# ---------------------------------------------------------------------------
# _switch / _promote / _confirm_refused preconditions (C-17 L1469, 1536, 1617)
# ---------------------------------------------------------------------------

def test_switch_aborts_when_the_live_key_file_is_neither_old_nor_new(bed):
    _crash_at(bed, "after_publish")
    kp = Path(bed.identity(KS).key_path)
    kp.write_text("fok_test-someone-replaced-the-key\n")
    code, summary = bed.rotator().run_once()
    assert summary["result"] == "aborted" and summary["reason_class"] == "io", summary
    assert summary["phase"] == "switch"
    assert kp.read_text() == "fok_test-someone-replaced-the-key\n"
    assert not Path(str(kp) + ".prev").exists()


def test_switch_aborts_when_the_next_key_file_is_gone(bed):
    r, j, identity = _stalled(bed, "after_publish", "switch")
    old = bed.key_sha(KS)
    os.unlink(identity.key_path + ".next")
    with pytest.raises(rot._Stop) as ei:
        r._switch(j, identity)
    assert ei.value.summary["reason_class"] == "io"
    assert bed.key_sha(KS) == old


@pytest.mark.parametrize("fault", ["key_other", "key_missing", "row_missing"])
def test_promote_refuses_when_the_key_file_or_row_is_not_the_journals(bed, fault):
    r, j, identity = _stalled(bed, "after_switch", "promote")
    if fault == "key_other":
        Path(identity.key_path).write_text("fok_test-another-key\n")
    elif fault == "key_missing":
        os.unlink(identity.key_path)
    else:
        doc = bed.live()
        doc["operators"] = [x for x in doc["operators"] if x["operator_id"] != KS]
        _write_doc(bed, doc)
    ops = bed.ops.read_bytes()
    with pytest.raises(rot._Stop) as ei:
        r._promote(j, identity)
    assert ei.value.summary["reason_class"] == "internal" and ei.value.summary["phase"] == "promote"
    assert bed.ops.read_bytes() == ops
    assert bed.estate.of("keyrotation.retired") == []


@pytest.mark.parametrize("fault", ["prev_other", "prev_missing"])
def test_confirm_refused_refuses_without_the_old_key_file(bed, fault):
    r, j, identity = _stalled(bed, "after_switch", "confirm_refused")
    prev = Path(identity.key_path + ".prev")
    if fault == "prev_other":
        prev.write_text("fok_test-not-the-old-key\n")
    else:
        os.unlink(prev)
    with pytest.raises(rot._Stop) as ei:
        r._confirm_refused(j, identity)
    assert ei.value.summary["reason_class"] == "io"
    assert ei.value.summary["phase"] == "confirm_refused"


# ---------------------------------------------------------------------------
# _restore_format1 (C-17 L1267): only the exact bytes the run read
# ---------------------------------------------------------------------------

def test_migration_registry_error_does_not_restore_over_a_changed_kept_copy(tmp_path):
    from test_rotation_r4a import _format1_bed
    bed = _format1_bed(tmp_path)

    def hook(point):
        if point == "after_operators_write":
            (bed.state / rot.PREV_NAME).write_bytes(b'[{"operator_id": "x"}]')
            bed.estate.services["kill-switch"].force_error = "operator registry malformed"
    code, summary = bed.rotator(hook=hook).run_once()
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "registry_error", summary
    assert summary["reverted"] is False
    assert json.loads(bed.ops.read_text())["format"] == 2          # nothing written over it
    assert bed.estate.of("keyrotation.failed")[0]["reverted"] is False


# ---------------------------------------------------------------------------
# PUBLISH / GENERATE crash recovery (C-17 L1365, L1389-1397)
# ---------------------------------------------------------------------------

def test_a_lost_next_file_with_a_published_next_key_aborts(bed):
    identity = _crash_at(bed, "after_publish")
    os.unlink(identity.key_path + ".next")
    code, summary = bed.rotator().run_once()
    assert summary["result"] == "aborted" and summary["reason_class"] == "io", summary
    assert "next_key" not in bed.row(KS)               # the abort took the published slot out


def test_a_lost_next_file_before_publish_generates_a_fresh_key(bed):
    identity = _crash_at(bed, "before_operators_write")
    nxt = Path(identity.key_path + ".next")
    lost = rot.key_file_sha(nxt)
    os.unlink(nxt)
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    assert bed.key_sha(KS) != lost and bed.row(KS)["key_sha256"] == bed.key_sha(KS)
    assert bed.estate.types().count("keyrotation.published") == 1


def test_a_next_file_that_is_not_the_journals_key_is_regenerated_not_published(bed):
    identity = _crash_at(bed, "before_operators_write")
    nxt = Path(identity.key_path + ".next")
    nxt.write_text("fok_test-a-key-the-journal-never-saw\n")
    other = rot.key_file_sha(nxt)
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    assert bed.key_sha(KS) != other


def test_a_kept_next_file_of_the_journal_is_reused_on_resume(bed):
    identity = _crash_at(bed, "after_generate")
    kept = rot.key_file_sha(Path(identity.key_path + ".next"))
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    assert bed.key_sha(KS) == kept


def test_a_published_next_key_that_is_not_ours_aborts_at_publish(bed):
    r, j, identity = _stalled(bed, "after_publish", "publish")
    doc = bed.live()
    row = next(x for x in doc["operators"] if x["operator_id"] == KS)
    row["next_key"] = {**row["next_key"], "key_sha256": sha("fok_someone-elses-key")}
    _write_doc(bed, doc)
    with pytest.raises(rot._Stop) as ei:
        r._do_publish(j, identity)
    assert ei.value.summary["reason_class"] == "foreign_edit"


def test_a_missing_row_at_publish_aborts_as_a_foreign_edit(bed):
    r, j, identity = _stalled(bed, "after_generate", "publish")
    doc = bed.live()
    doc["operators"] = [x for x in doc["operators"] if x["operator_id"] != KS]
    _write_doc(bed, doc)
    with pytest.raises(rot._Stop) as ei:
        r._do_publish(j, identity)
    assert ei.value.summary["reason_class"] == "foreign_edit"


# ---------------------------------------------------------------------------
# keyrotation.retired after a revert and retry (C-17 L1575, L1609)
# ---------------------------------------------------------------------------

def test_a_retry_after_a_verify_current_revert_ledgers_the_second_promote(bed):
    state = {"fail": True}

    def lie(oid, key_sha, ans):
        if state["fail"] and oid == KS and ans["matched"] == "current":
            return {**ans, "matched": "none"}
        return ans
    # the lie starts only once PROMOTE has been written
    def hook(point):
        if point == "after_promote":
            bed.estate.services["federation-broker"].answer_hook = lie
    code, _ = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    state["fail"] = False
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    retired = bed.estate.of("keyrotation.retired")
    assert len(retired) == 2 and retired[0]["generation"] < retired[1]["generation"]
    assert retired[1]["generation"] == summary["generation"]


# ---------------------------------------------------------------------------
# the waits (C-17 L806, L822): they poll until the deadline, not once
# ---------------------------------------------------------------------------

def test_publish_wait_polls_until_every_service_shows_the_file(bed):
    svc = bed.estate.services["federation-broker"]
    real_sleep, n = bed.estate.sleep, {"n": 0}

    def sleep(seconds):
        real_sleep(seconds)
        n["n"] += 1
        if n["n"] >= 3:
            svc.frozen = None
    first = {"done": False}
    # the service serves the pre-publish file until the third poll
    pre = bed.ops.read_bytes()

    def hook2(point):
        if point == "before_operators_write" and not first["done"]:
            first["done"] = True
            svc.frozen = pre
            bed.estate.sleep = sleep
    code, summary = bed.rotator(hook=hook2).run_once(now_id=KS)
    assert code == 0 and summary["result"] == "completed", summary
    assert n["n"] >= 3


def test_publish_wait_gives_up_only_at_the_deadline(bed):
    svc = bed.estate.services["federation-broker"]
    pre = bed.ops.read_bytes()

    def hook(point):
        if point == "before_operators_write":
            svc.frozen = pre
    code, summary = bed.rotator(hook=hook, publish_wait_s=60, poll_s=5).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "publish_not_seen", summary
    assert bed.estate.sleeps >= 60                                  # waited the whole window


def test_confirm_switch_polls_the_daemon_until_the_deadline(bed):
    svc = bed.estate.services["kill-switch"]
    real_sleep, n = bed.estate.sleep, {"n": 0}

    def sleep(seconds):
        real_sleep(seconds)
        n["n"] += 1
        if n["n"] >= 2:
            svc.stuck_fp = None

    def hook(point):
        if point == "after_switch":
            svc.stuck_fp = "0" * 16
            bed.estate.sleep = sleep
    code, summary = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == 0 and summary["result"] == "completed", summary
    assert n["n"] >= 2


def test_confirm_switch_gives_up_after_confirm_switch_s(bed):
    svc = bed.estate.services["kill-switch"]
    s = bed.settings()

    def hook(point):
        if point == "after_switch":
            svc.stuck_fp = "0" * 16
    code, summary = bed.rotator(hook=hook).run_once(now_id=KS)
    assert summary["reason_class"] == "switch_not_seen", summary
    assert bed.estate.sleeps >= s.confirm_switch_s


# ---------------------------------------------------------------------------
# the 24 h limit and a journal for an identity not managed here
# ---------------------------------------------------------------------------

def test_the_24h_limit_applies_at_exactly_24h_and_not_a_second_before(bed):
    assert bed.rotator(max_wait_s=0).run_once(now_id=KS)[1]["result"] == "in_progress"
    started = _journal(bed).started_at
    bed.estate.t = started + rot.INFLIGHT_LIMIT_S - 1
    code, summary = bed.rotator(max_wait_s=0).run_once()
    assert summary["result"] != "aborted", summary                  # one second early: not aborted
    # a second journal state, the limit reached exactly
    bed2 = Bed(bed.root / "second")
    assert bed2.rotator(max_wait_s=0).run_once(now_id=KS)[1]["result"] == "in_progress"
    bed2.estate.t = _journal(bed2).started_at + rot.INFLIGHT_LIMIT_S
    code, summary = bed2.rotator(max_wait_s=0).run_once()
    assert summary["result"] == "aborted" and summary["reason_class"] == "timeout", summary


def test_a_journal_for_an_identity_not_managed_here_halts(bed):
    j = rot.Journal(run_id="r", operator_id="ghost", reason="schedule", started_at=int(T0))
    (bed.state / "journal-ghost.json").write_bytes(j.to_bytes())
    ops = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "internal", summary
    assert bed.ops.read_bytes() == ops


# ---------------------------------------------------------------------------
# --dry-run is free of side effects on every skip path (C-17 L1038..1203)
# ---------------------------------------------------------------------------

def _dry_lock(bed):
    lock = rot._EstateLock(bed.state / rot.LOCK_NAME)
    lock.acquire()
    return lock.release


def _dry_clock(bed):
    bed.estate.synced = False


def _dry_issued(bed):
    doc = bed.live()
    doc["issued_at"] = oa.format_time(T0 + 3600)
    _write_doc(bed, doc)


def _dry_build(bed):
    bed.estate.builds["kill-switch"] = "other"


def _dry_freeze(bed):
    (bed.state / rot.FREEZE_NAME).write_text("freeze\n")


def _dry_journal_unreadable(bed):
    (bed.state / "journal-svc-killswitch.json").write_text("{not json")


def _dry_journal_in_flight(bed):
    assert bed.rotator(max_wait_s=0).run_once(now_id=KS)[1]["result"] == "in_progress"


def _dry_precheck(bed):
    bed.estate.services["lifecycle-manager"].frozen = b'{"format": 2}'


def _dry_foreign(bed):
    assert bed.rotator().run_once(now_id=KS)[0] == 0
    bed.estate.t += rot.ESTATE_SPACING_S
    doc = bed.live()
    doc["operators"][1]["scopes"] = ["*"]
    _write_doc(bed, doc)


@pytest.mark.parametrize("setup", [_dry_lock, _dry_clock, _dry_issued, _dry_build, _dry_freeze,
                                   _dry_journal_unreadable, _dry_journal_in_flight,
                                   _dry_precheck, _dry_foreign])
def test_dry_run_on_a_skip_path_ledgers_and_writes_nothing(bed, setup):
    release = setup(bed)
    try:
        events = len(bed.estate.events)
        files = _files(bed)
        ops = bed.ops.read_bytes()
        status = (bed.state / rot.STATUS_NAME).read_bytes() \
            if (bed.state / rot.STATUS_NAME).exists() else None
        code, summary = bed.rotator().run_once(dry_run=True)
    finally:
        if release:
            release()
    assert code != 0 or summary["result"] == "dry_run", summary
    assert len(bed.estate.events) == events, bed.estate.events[events:]
    assert _files(bed) == files and bed.ops.read_bytes() == ops
    after = (bed.state / rot.STATUS_NAME).read_bytes() \
        if (bed.state / rot.STATUS_NAME).exists() else None
    assert after == status


# ---------------------------------------------------------------------------
# C-16 finding 1: a crash after the migration write is still ledgered
# ---------------------------------------------------------------------------

def test_a_crash_after_the_migration_write_is_ledgered_by_the_next_run(tmp_path):
    from test_rotation_r4a import _format1_bed
    bed = _format1_bed(tmp_path)

    def hook(point):
        if point == "after_operators_write":
            raise Crash()
    with pytest.raises(Crash):
        bed.rotator(hook=hook).run_once()
    assert bed.estate.of("keyrotation.reconciled") == []
    code, summary = bed.rotator().run_once(dry_run=True)
    assert bed.estate.of("keyrotation.reconciled") == []            # a dry run ledgers nothing
    code, summary = bed.rotator().run_once()
    assert code == 0, summary
    rec = bed.estate.of("keyrotation.reconciled")
    assert len(rec) == 1 and rec[0]["generation"] == bed.live()["generation"]
    assert rec[0]["registry_sha16"] == rot.sha256_hex(bed.ops.read_bytes())[:16]
    assert rec[0]["operator_ids"] and "migration_pending" not in json.loads(
        (bed.state / rot.STATUS_NAME).read_text()) or json.loads(
        (bed.state / rot.STATUS_NAME).read_text())["migration_pending"] is None
    bed.rotator().run_once()
    assert len(bed.estate.of("keyrotation.reconciled")) == 1        # once


def test_a_migration_refused_before_the_write_leaves_no_pending_marker(tmp_path, monkeypatch):
    from test_rotation_r4a import _format1_bed
    bed = _format1_bed(tmp_path)

    def refuse(*a, **k):
        raise rot.PolicyRefused("no")
    monkeypatch.setattr(rot, "diff_guard", refuse)
    bed.rotator().run_once()
    st = json.loads((bed.state / rot.STATUS_NAME).read_text()) \
        if (bed.state / rot.STATUS_NAME).exists() else {}
    assert st.get("migration_pending") is None


# ---------------------------------------------------------------------------
# C-16 finding 2: deleting the status file does not switch detection off
# ---------------------------------------------------------------------------

def test_a_foreign_edit_after_the_status_file_is_deleted_is_still_detected(bed):
    assert bed.rotator().run_once(now_id=KS)[1]["result"] == "completed"
    bed.estate.t += rot.ESTATE_SPACING_S
    doc = bed.live()
    next(r for r in doc["operators"] if r["operator_id"] == REG)["scopes"] = ["*"]
    _write_doc(bed, doc)
    os.unlink(bed.state / rot.STATUS_NAME)
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_SKIPPED and summary["skip_reason"] == "foreign_edit", summary
    assert bed.ops.read_bytes() == before


def test_a_deleted_status_file_with_an_unchanged_operators_file_is_not_a_foreign_edit(bed):
    assert bed.rotator().run_once(now_id=KS)[1]["result"] == "completed"
    bed.estate.t += rot.ESTATE_SPACING_S
    os.unlink(bed.state / rot.STATUS_NAME)
    code, summary = bed.rotator().run_once(now_id=REG)
    assert code == 0 and summary["result"] == "completed", summary


# ---------------------------------------------------------------------------
# condition 2: the post-PROMOTE retry cap
# ---------------------------------------------------------------------------

def _failing_verify_current(bed):
    state = {"on": False}

    def hook(point):
        if point == "after_promote":
            state["on"] = True

    def lie(oid, key_sha, ans):
        if state["on"] and oid == KS and ans["matched"] == "current":
            return {**ans, "matched": "none"}
        return ans
    bed.estate.services["federation-broker"].answer_hook = lie
    return hook, state


def test_a_persistent_post_promote_failure_halts_after_the_cap_with_a_critical_log(bed, caplog):
    hook, state = _failing_verify_current(bed)
    code, _ = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    assert _journal(bed).post_promote_failures == 1
    for _ in range(rot.POST_PROMOTE_MAX_FAILURES - 1):
        code, summary = bed.rotator().run_once()
        assert code == rot.EXIT_FAILED and "halted" not in summary, summary
    assert _journal(bed).post_promote_failures == rot.POST_PROMOTE_MAX_FAILURES
    ops = bed.ops.read_bytes()
    keys = (bed.key_sha(KS), Path(bed.identity(KS).key_path + ".prev").read_bytes())
    caplog.clear()
    with caplog.at_level("CRITICAL"):
        code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["halted"] is True, summary
    assert any(r.levelname == "CRITICAL" for r in caplog.records)
    assert bed.ops.read_bytes() == ops                              # nothing written
    assert keys == (bed.key_sha(KS), Path(bed.identity(KS).key_path + ".prev").read_bytes())
    failed = bed.estate.of("keyrotation.failed")[-1]
    assert failed["reason_class"] == "internal" and failed["reverted"] is False   # hourly alert
    assert json.loads((bed.state / rot.STATUS_NAME).read_text())["halted"]["operator_id"] == KS
    # the cap is the only thing stopping it: one fewer failure and it retries
    j = _journal(bed)
    j.post_promote_failures = rot.POST_PROMOTE_MAX_FAILURES - 1
    (bed.state / f"journal-{KS}.json").write_bytes(j.to_bytes())
    state["on"] = False
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary


def test_an_old_journal_without_the_failure_counter_still_loads():
    j = rot.Journal.from_bytes(json.dumps({"run_id": "r", "operator_id": KS, "reason": "schedule",
                                           "started_at": 1, "phase": "promote"}).encode())
    assert j.post_promote_failures == 0


def test_the_cap_does_not_apply_before_promote(bed):
    r, j, identity = _stalled(bed, "after_switch", "soak")
    j.post_promote_failures = 99
    (bed.state / f"journal-{KS}.json").write_bytes(j.to_bytes())
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
