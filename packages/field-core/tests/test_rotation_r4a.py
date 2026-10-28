"""Key rotation slice R4a: the rotator core (field_core.rotation) driven
against fakes of the eight services that use the REAL R1 parser and the REAL
retired-hash memory (rotation_fakes_r4a). Design v0.2 section 4.3 (the
sequence), 4.4 (crash, abort), 2.2 (migration), 2.4 (rollback containment),
and the reviews' carry-forwards: auto-revert after PROMOTE re-publishes .prev
at a new generation (R1 review F2); every post-restore write goes above the
highest generation ever issued (R1 review-2 F6); the migration normalises
keygen's +00:00 created_at and is validated by the same parser (R1 review 5d,
5f). Every key is a fake test value made in a temp directory."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rotation_fakes_r4a import (  # noqa: E402
    ROTATOR_ID, T0, Bed, Crash, sha)

from field_core import operator_auth as oa  # noqa: E402
from field_core import rotation as rot  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
HEX64 = re.compile(r"[0-9a-f]{64}")
KS = "svc-killswitch"


@pytest.fixture(autouse=True)
def _fresh_memory(monkeypatch):
    oa.reset_retired_memory()
    if os.name == "nt":
        # fsync costs ~0.3 s a call on a Windows dev disk; CI (Linux) keeps it
        monkeypatch.setattr(rot.os, "fsync", lambda fd: None)
    yield
    oa.reset_retired_memory()


@pytest.fixture
def bed(tmp_path):
    return Bed(tmp_path)


def _all_answer(bed, oid, key_sha):
    return {svc: s.verify_hash(oid, key_sha) for svc, s in bed.estate.services.items()}


# --------------------------------------------------------------------------
# the full sequence
# --------------------------------------------------------------------------

def test_full_rotation_of_a_daemon_identity(bed):
    old_sha = bed.key_sha(KS)
    before = bed.live()
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_OK, summary
    assert summary["result"] == "completed"
    new_sha = bed.key_sha(KS)
    assert new_sha != old_sha
    row = bed.row(KS)
    assert row["key_sha256"] == new_sha and "next_key" not in row
    assert row["key_created_at"] == oa.format_time(int(bed.estate.t))
    assert oa.parse_time(row["key_not_after"]) == int(bed.estate.t) + rot.KEY_LIFETIME_S
    # the old key file is gone only after 9b and 10; the pre-publish copy is
    # replaced by the promoted file (S4)
    kp = Path(bed.identity(KS).key_path)
    assert not Path(str(kp) + ".prev").exists() and not Path(str(kp) + ".next").exists()
    assert (bed.state / rot.PREV_NAME).read_bytes() == bed.ops.read_bytes()
    assert not list(bed.state.glob("journal-*"))
    st = json.loads((bed.state / rot.STATUS_NAME).read_text())
    assert st["in_flight"] is None and st["last_result"] == "completed"
    assert st["completed"][KS] == st["last_completed_at"]
    assert bed.estate.types() == ["keyrotation.started", "keyrotation.published",
                                  "keyrotation.cutover", "keyrotation.retired",
                                  "keyrotation.completed"]
    pub, ret, done = (bed.estate.of(t)[0] for t in ("keyrotation.published",
                                                     "keyrotation.retired",
                                                     "keyrotation.completed"))
    assert pub["generation"] == 11 and ret["generation"] == 12 == done["generation"]
    assert done["old_fp"] == old_sha[:16] and done["new_fp"] == new_sha[:16]
    assert ret["registry_sha16"] == rot.sha256_hex(bed.ops.read_bytes())[:16]
    # nothing but the target's key fields and the header changed
    after = bed.live()
    rot.diff_guard(before, after, [KS])
    for a, b in zip(before["operators"], after["operators"]):
        if a["operator_id"] != KS:
            assert a == b
    # every service: the new key is current, the old one is gone
    for ans in _all_answer(bed, KS, new_sha).values():
        assert ans["matched"] == "current" and ans["matchable_now"] and not ans["retired"]
    for ans in _all_answer(bed, KS, old_sha).values():
        assert ans["matched"] == "none"


def test_verify_next_happens_on_all_eight_before_the_key_file_switches(bed):
    seen = {}

    def hook(point):
        if point == "after_switch":
            nxt_sha = bed.key_sha(KS)
            seen["verified"] = {svc for svc, oid, s in bed.estate.verify_calls
                                if oid == KS and s == nxt_sha}
    code, _ = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == 0
    assert seen["verified"] == set(rot.SERVICES)


def test_old_key_file_kept_until_verify_current_and_confirm_refused(bed):
    old_sha = bed.key_sha(KS)
    kp = Path(bed.identity(KS).key_path)
    snapshots = []

    def hook(point):
        if point == "after_promote":
            snapshots.append(rot.key_file_sha(Path(str(kp) + ".prev")))
    assert bed.rotator(hook=hook).run_once(now_id=KS)[0] == 0
    assert snapshots == [old_sha]
    # 9b asked for the LIVE key as current and 10 for the old key as none, on all eight
    new_sha = bed.key_sha(KS)
    assert {svc for svc, _, s in bed.estate.verify_calls if s == new_sha} == set(rot.SERVICES)
    assert {svc for svc, _, s in bed.estate.verify_calls if s == old_sha} == set(rot.SERVICES)


def test_job_and_self_identities_rotate_without_a_daemon_check(bed):
    for oid in ("job-provision-gb10", ROTATOR_ID):
        old = bed.key_sha(oid)
        code, summary = bed.rotator().run_once(now_id=oid)
        assert code == 0 and summary["result"] == "completed", summary
        assert bed.key_sha(oid) != old and bed.row(oid)["key_sha256"] == bed.key_sha(oid)


def test_self_rotation_aborts_when_the_cutover_append_shows_another_key(bed):
    orig = bed.estate.append

    def append(event_type, payload):
        out = orig(event_type, payload)
        if event_type == "keyrotation.cutover":
            out["payload"]["operator_key_fp"] = "deadbeef"
        return out
    bed.estate.append = append
    old = bed.key_sha(ROTATOR_ID)
    code, summary = bed.rotator().run_once(now_id=ROTATOR_ID)
    assert code == rot.EXIT_FAILED and summary["result"] == "aborted"
    assert summary["reason_class"] == "switch_not_seen"
    assert bed.key_sha(ROTATOR_ID) == old


# --------------------------------------------------------------------------
# keys never leave the host; files are 0600
# --------------------------------------------------------------------------

def test_the_new_key_is_never_printed_logged_ledgered_or_journaled(bed, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    captured = []

    def hook(point):
        for p in bed.state.iterdir():
            if p.is_file() and p.name != rot.LOCK_NAME:
                captured.append(p.read_bytes())
    _, summary = bed.rotator(hook=hook).run_once(now_id=KS)
    assert summary["result"] == "completed", summary
    new_key = oa._key_from_file(bed.identity(KS).key_path)
    assert new_key.startswith(oa.KEY_PREFIX) and new_key != bed.key_values[KS]
    assert len(captured) >= 7
    new_sha = oa.key_sha256(new_key)
    out = capsys.readouterr()
    blobs = [out.out, out.err, caplog.text, json.dumps(bed.estate.events),
             json.dumps(summary)]
    blobs += [b.decode("utf-8", "replace") for b in captured
              if b"operators" not in b]          # journal, status (not the .prev copy)
    for blob in blobs:
        assert new_key not in blob
        assert new_sha not in blob
    assert new_key not in bed.ops.read_text()
    for _, payload in bed.estate.events:
        assert not HEX64.search(json.dumps(payload))


def test_files_are_created_exclusive_and_0600(bed, monkeypatch):
    opened = []
    real_open = os.open

    def recording_open(path, flags, mode=0o777, *a, **kw):
        opened.append((str(path), flags, mode))
        return real_open(path, flags, mode, *a, **kw)
    monkeypatch.setattr(rot.os, "open", recording_open)
    assert bed.rotator().run_once(now_id=KS)[0] == 0
    kp = bed.identity(KS).key_path
    nxt = [o for o in opened if o[0] == kp + ".next"]
    assert nxt and all(f & os.O_EXCL and f & os.O_CREAT and m == 0o600 for _, f, m in nxt)
    for name in ("journal-", "status.json", "operators.json.prev"):
        tmps = [o for o in opened if name in Path(o[0]).name and o[0].endswith(".tmp")]
        assert tmps, name
        assert all(f & os.O_EXCL and m == 0o600 for _, f, m in tmps), name
    lock = [o for o in opened if o[0].endswith(rot.LOCK_NAME)]
    assert lock and all(m == 0o600 for _, _, m in lock)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_real_modes_are_0600_on_posix(bed):
    kp = bed.identity(KS).key_path
    modes = {}

    def hook(point):
        if point == "after_generate":
            modes["next"] = os.stat(kp + ".next").st_mode & 0o777
            modes["journal"] = os.stat(bed.state / f"journal-{KS}.json").st_mode & 0o777
            modes["status"] = os.stat(bed.state / rot.STATUS_NAME).st_mode & 0o777
        if point == "after_key_prev":
            modes["key_prev"] = os.stat(kp + ".prev").st_mode & 0o777
    assert bed.rotator(hook=hook).run_once(now_id=KS)[0] == 0
    modes["ops_prev"] = os.stat(bed.state / rot.PREV_NAME).st_mode & 0o777
    modes["lock"] = os.stat(bed.state / rot.LOCK_NAME).st_mode & 0o777
    assert modes == {k: 0o600 for k in ("next", "journal", "status", "key_prev",
                                         "ops_prev", "lock")}


# --------------------------------------------------------------------------
# auto-revert, abort, 9b (R1 review F2)
# --------------------------------------------------------------------------

def test_a_registry_error_after_publish_reverts_with_its_own_reason(bed):
    def hook(point):
        if point == "after_operators_write" and not bed.estate.of("keyrotation.failed"):
            bed.estate.services["kill-switch"].force_error = "operator registry malformed"
    old_sha = bed.key_sha(KS)
    code, summary = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["phase"] == "publish" and failed["reason_class"] == "registry_error"
    assert failed["reverted"] is True and "next_key" not in bed.row(KS)
    assert bed.key_sha(KS) == old_sha


def test_publish_not_seen_reverts_by_republishing_above_the_published_generation(bed):
    bed.estate.services["spend-governor"].frozen = bed.ops.read_bytes()
    old_sha = bed.key_sha(KS)
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["reverted"] is True
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["phase"] == "publish" and failed["reason_class"] == "publish_not_seen"
    assert failed["reverted"] is True and failed["generation"] == 12
    live = bed.live()
    assert live["generation"] == 12 and "next_key" not in bed.row(KS)
    assert bed.key_sha(KS) == old_sha
    assert not Path(bed.identity(KS).key_path + ".next").exists()
    assert not list(bed.state.glob("journal-*"))
    bed.estate.services["spend-governor"].frozen = None
    for ans in _all_answer(bed, KS, old_sha).values():
        assert ans["matched"] == "current" and ans["matchable_now"]


def test_verify_current_failure_republishes_prev_at_a_new_generation_and_both_keys_stay_valid(bed):
    """R1 review F2: after PROMOTE the auto-revert must re-publish the .prev
    content ABOVE the promoted generation; renaming .prev back (a lower
    generation) makes every verifier that saw the promoted file refuse the old
    key (retired-hash memory), a denial-of-kill for svc-killswitch."""
    old_sha = bed.key_sha(KS)
    state = {"promoted": False}

    def hook(point):
        if point == "after_promote":
            state["promoted"] = True
            # every service loads the promoted file (and remembers the old
            # hash as removed at that generation)
            for s in bed.estate.services.values():
                s.rotation_state()

    def lie(oid, key_sha, ans):
        if state["promoted"] and oid == KS and ans["matched"] == "current":
            return {**ans, "matched": "none"}
        return ans
    bed.estate.services["federation-broker"].answer_hook = lie
    code, summary = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED, summary
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["phase"] == "verify_current" and failed["reverted"] is True
    promoted = bed.estate.of("keyrotation.retired")[0]["generation"]
    assert failed["generation"] > promoted
    new_sha = bed.key_sha(KS)
    row = bed.row(KS)
    assert row["key_sha256"] == old_sha and row["next_key"]["key_sha256"] == new_sha
    assert bed.live()["generation"] == failed["generation"]
    bed.estate.services["federation-broker"].answer_hook = None
    for ans in _all_answer(bed, KS, old_sha).values():
        assert ans["matched"] == "current" and ans["matchable_now"] and not ans["retired"]
    for ans in _all_answer(bed, KS, new_sha).values():
        assert ans["matched"] == "next" and ans["matchable_now"] and not ans["retired"]
    assert rot.key_file_sha(Path(bed.identity(KS).key_path + ".prev")) == old_sha
    journal = json.loads((bed.state / f"journal-{KS}.json").read_text())
    assert journal["phase"] == "soak"
    # the next run promotes again and completes
    state["promoted"] = False
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    assert bed.row(KS)["key_sha256"] == new_sha


def test_promote_not_seen_republishes_prev_above_the_promoted_generation(bed):
    old_sha = bed.key_sha(KS)

    def hook(point):
        if point == "before_operators_write" and bed.estate.of("keyrotation.cutover"):
            bed.estate.services["ops-console"].frozen = bed.ops.read_bytes()
    code, summary = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["phase"] == "promote" and failed["reverted"] is True
    assert failed["generation"] == 13
    assert bed.row(KS)["key_sha256"] == old_sha
    bed.estate.services["ops-console"].frozen = None
    for ans in _all_answer(bed, KS, old_sha).values():
        assert ans["matchable_now"] and not ans["retired"]


@pytest.mark.parametrize("lie", ["not_matchable", "retired", "as_current", "none", "error"])
def test_verify_next_mismatch_aborts_before_anything_switches(bed, lie):
    old_sha = bed.key_sha(KS)

    def hook(oid, s, ans):
        if ans["matched"] != "next":
            return ans
        if lie == "error":
            raise rot.EstateError("down")
        return {**ans, **{"not_matchable": {"matchable_now": False},
                          "retired": {"retired": True},
                          "as_current": {"matched": "current"},
                          "none": {"matched": "none", "matchable_now": False}}[lie]}
    bed.estate.services["kill-switch"].answer_hook = hook
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["result"] == "aborted"
    aborted = bed.estate.of("keyrotation.aborted")[0]
    assert aborted["phase"] == "verify_next" and aborted["reason_class"] == "verify_mismatch"
    assert aborted["reverted"] is True and aborted["generation"] == 12
    assert bed.key_sha(KS) == old_sha
    row = bed.row(KS)
    assert row["key_sha256"] == old_sha and "next_key" not in row
    assert not Path(bed.identity(KS).key_path + ".next").exists()
    assert "keyrotation.cutover" not in bed.estate.types()


def test_confirm_switch_failure_restores_the_old_key_file(bed):
    old_sha = bed.key_sha(KS)
    bed.estate.services["kill-switch"].stuck_fp = old_sha[:16]
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["result"] == "aborted"
    aborted = bed.estate.of("keyrotation.aborted")[0]
    assert aborted["reason_class"] == "switch_not_seen" and aborted["phase"] == "confirm_switch"
    assert "keyrotation.cutover" not in bed.estate.types()
    kp = bed.identity(KS).key_path
    assert bed.key_sha(KS) == old_sha
    assert not Path(kp + ".prev").exists() and not Path(kp + ".next").exists()
    assert "next_key" not in bed.row(KS)


def test_refusal_during_soak_aborts(bed):
    old_sha = bed.key_sha(KS)

    def hook(point):
        if point == "after_switch":
            bed.estate.refusal_log.append((KS, bed.estate.t + 1))
    code, summary = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    assert bed.estate.of("keyrotation.aborted")[0]["reason_class"] == "refusal_seen"
    assert bed.key_sha(KS) == old_sha and "next_key" not in bed.row(KS)


def test_confirm_refused_failure_keeps_the_old_key_file_for_the_next_run(bed):
    old_sha = bed.key_sha(KS)
    bed.estate.services["sealed-ledger"].answer_hook = (
        lambda oid, s, ans: {**ans, "matched": "current", "matchable_now": True}
        if s == old_sha else ans)
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["phase"] == "confirm_refused" and failed["reverted"] is False
    kp = bed.identity(KS).key_path
    assert rot.key_file_sha(Path(kp + ".prev")) == old_sha
    assert json.loads((bed.state / f"journal-{KS}.json").read_text())["phase"] == "confirm_refused"
    bed.estate.services["sealed-ledger"].answer_hook = None
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed"
    assert not Path(kp + ".prev").exists()


def test_inflight_rotation_older_than_24h_before_promote_is_aborted(bed):
    old_sha = bed.key_sha(KS)
    code, summary = bed.rotator(max_wait_s=0).run_once(now_id=KS)
    assert code == 0 and summary["result"] == "in_progress"
    assert bed.key_sha(KS) != old_sha
    bed.estate.t += rot.INFLIGHT_LIMIT_S + 1
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["result"] == "aborted"
    assert bed.estate.of("keyrotation.aborted")[0]["reason_class"] == "timeout"
    assert bed.key_sha(KS) == old_sha and "next_key" not in bed.row(KS)


def test_promote_refuses_a_hash_other_than_the_live_key_file(bed):
    """design 4.3 step 9: PROMOTE writes sha256(live key file) and nothing
    else; a key file that no longer matches the published NEXT slot is never
    promoted."""
    def hook(point):
        if point == "before_operators_write" and bed.estate.of("keyrotation.cutover"):
            raise Crash()                      # the PROMOTE write, not yet made
    with pytest.raises(Crash):
        bed.rotator(hook=hook).run_once(now_id=KS)
    published = bed.row(KS)["next_key"]["key_sha256"]
    kp = Path(bed.identity(KS).key_path)
    kp.write_text("fok_test-tampered-not-a-real-key\n", encoding="utf-8")
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED, summary
    assert summary["phase"] == "promote"
    assert bed.ops.read_bytes() == before
    assert bed.row(KS)["next_key"]["key_sha256"] == published
    assert "keyrotation.retired" not in bed.estate.types()


def test_promote_writes_exactly_the_live_key_hash(bed):
    def hook(point):
        if point == "after_promote":
            assert bed.row(KS)["key_sha256"] == bed.key_sha(KS)
    assert bed.rotator(hook=hook).run_once(now_id=KS)[0] == 0


# --------------------------------------------------------------------------
# generations (R1 review-2 F6)
# --------------------------------------------------------------------------

def test_writes_go_above_the_highest_generation_ever_issued_after_a_restore(bed):
    """A file at generation 50 was live (every service saw it), then an older
    file (generation 10) came back. A write at live + 1 = 11 would have the new
    NEXT hash refused by every verifier (it is not in the generation 50 file
    and 11 < 50), so VERIFY-NEXT fails; the rotator writes at 51."""
    restored = bed.ops.read_bytes()
    high = json.loads(restored)
    high["generation"] = 50
    bed.ops.write_bytes(rot.encode_doc(high))
    for s in bed.estate.services.values():
        s.rotation_state()            # every verifier learns generation 50
    bed.ops.write_bytes(restored)     # the restore (re-baselined below)
    rot._write_private(bed.state / rot.STATUS_NAME, json.dumps(
        {"high_generation": 50, "last_written_sha256": rot.sha256_hex(restored)}).encode())
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == 0 and summary["result"] == "completed", summary
    assert bed.estate.of("keyrotation.published")[0]["generation"] == 51
    assert bed.estate.of("keyrotation.retired")[0]["generation"] == 52
    st = json.loads((bed.state / rot.STATUS_NAME).read_text())
    assert st["high_generation"] == 52


def test_next_generation_also_counts_service_reported_generations(bed):
    states = {svc: {"registry_generation": 7} for svc in rot.SERVICES}
    states["kill-switch"] = {"registry_generation": 77}
    r = bed.rotator()
    assert r._next_generation(bed.live(), states) == 78
    rot._write_private(bed.state / rot.STATUS_NAME, b'{"high_generation": 90}')
    assert r._next_generation(bed.live(), states) == 91


def test_the_high_water_mark_is_recorded_before_the_file_is_written(bed):
    seen = []

    def hook(point):
        if point == "before_operators_write":
            st = json.loads((bed.state / rot.STATUS_NAME).read_text())
            seen.append(st["high_generation"])
    assert bed.rotator(hook=hook).run_once(now_id=KS)[0] == 0
    assert seen == [11, 12]


# --------------------------------------------------------------------------
# crash and resume (design 4.4)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("point", ["after_next_written", "after_generate",
                                   "before_operators_write", "after_operators_write",
                                   "after_publish", "after_key_prev", "after_switch",
                                   "after_promote"])
def test_a_crash_at_each_phase_is_resumed_by_the_next_run(bed, point):
    calls = {"n": 0}

    def hook(p):
        if p == point:
            calls["n"] += 1
            if calls["n"] == 1:
                raise Crash()
    with pytest.raises(Crash):
        bed.rotator(hook=hook).run_once(now_id=KS)
    assert list(bed.state.glob("journal-*"))
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    row = bed.row(KS)
    assert row["key_sha256"] == bed.key_sha(KS) and "next_key" not in row
    for t in ("keyrotation.started", "keyrotation.published", "keyrotation.cutover",
              "keyrotation.retired", "keyrotation.completed"):
        assert bed.estate.types().count(t) == 1, (t, bed.estate.types())
    kp = bed.identity(KS).key_path
    assert not Path(kp + ".prev").exists() and not Path(kp + ".next").exists()
    oa.parse_registry_doc(bed.live(), require_active=True)


def test_soak_longer_than_the_run_budget_resumes_without_duplicate_events(bed):
    code, summary = bed.rotator(max_wait_s=60).run_once(now_id=KS)
    assert code == 0 and summary["result"] == "in_progress" and summary["phase"] == "soak"
    bed.estate.t += rot.MIN_SOAK_S
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed"
    assert bed.estate.types().count("keyrotation.cutover") == 1


def test_soak_is_at_least_fifteen_minutes_and_three_ticks(bed):
    r = bed.rotator(observer_tick_s=600)
    assert r._soak_seconds(bed.identity(KS)) == 1800
    r = bed.rotator(observer_tick_s=60)
    assert r._soak_seconds(bed.identity(KS)) == rot.MIN_SOAK_S
    start = bed.estate.t
    assert bed.rotator().run_once(now_id=KS)[0] == 0
    assert bed.estate.t - start >= rot.MIN_SOAK_S


def test_a_failed_ledger_append_stops_the_run_and_the_next_run_emits_it_once(bed):
    bed.estate.fail_append = {"keyrotation.published"}
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "io"
    assert list(bed.state.glob("journal-*"))
    bed.estate.fail_append = set()
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed"
    assert bed.estate.types().count("keyrotation.published") == 1


def test_an_unledgered_start_changes_nothing(bed):
    before = bed.ops.read_bytes()
    bed.estate.fail_append = {"keyrotation.started"}
    code, _ = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    assert bed.ops.read_bytes() == before
    assert not Path(bed.identity(KS).key_path + ".next").exists()
    assert not list(bed.state.glob("journal-*"))


# --------------------------------------------------------------------------
# incident, schedule, lock, freeze, preflight, foreign edit
# --------------------------------------------------------------------------

def test_incident_rotation_shortens_the_compromised_key_at_publish(bed):
    seen = {}

    def hook(point):
        if point == "after_publish":
            seen["not_after"] = oa.parse_time(bed.row(KS)["key_not_after"])
            seen["t"] = int(bed.estate.t)
    code, _ = bed.rotator(hook=hook).run_once(now_id=KS, reason="incident")
    assert code == 0
    assert seen["not_after"] == seen["t"] + rot.MIN_SOAK_S + rot.INCIDENT_EXTRA_S
    assert bed.estate.of("keyrotation.started")[0]["reason"] == "incident"


def test_schedule_picks_the_most_overdue_auto_identity_and_spaces_runs(bed):
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed"
    due = sorted(bed.identities, key=lambda i: rot.jitter_s(i.operator_id))[0]
    assert summary["operator_id"] == due.operator_id
    # 6 h spacing on the estate
    code, summary = bed.rotator().run_once()
    assert summary["result"] == "nothing_due"
    bed.estate.t += rot.ESTATE_SPACING_S
    code, summary = bed.rotator().run_once()
    assert summary["result"] == "completed" and summary["operator_id"] != due.operator_id


def test_fresh_keys_are_not_due(bed):
    doc = bed.live()
    for r in doc["operators"]:
        if r.get("rotation") == "auto":
            r["key_created_at"] = oa.format_time(T0 - 29 * rot.DAY)
    bed.ops.write_bytes(rot.encode_doc(doc))
    assert bed.rotator().run_once() == (0, {"result": "nothing_due"})


def test_lock_held_writes_nothing_and_exits_3(bed):
    before = bed.ops.read_bytes()
    lock = rot._EstateLock(bed.state / rot.LOCK_NAME)
    lock.acquire()
    try:
        code, summary = bed.rotator().run_once(now_id=KS)
    finally:
        lock.release()
    assert code == rot.EXIT_LOCKED and summary["skip_reason"] == "lock"
    assert bed.ops.read_bytes() == before
    assert bed.estate.of("keyrotation.skipped")[0]["operator_id"] is None


def test_freeze_skips(bed):
    (bed.state / rot.FREEZE_NAME).write_text("stage 2\n")
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_SKIPPED and summary["skip_reason"] == "freeze"
    assert bed.ops.read_bytes() == before


@pytest.mark.parametrize("breakage,reason", [("unsynced", "clock"), ("unknown_sync", "clock"),
                                             ("build", "precheck"), ("own_build", "precheck"),
                                             ("issued_future", "clock")])
def test_preflight_skips(bed, breakage, reason):
    kw = {}
    if breakage == "unsynced":
        bed.estate.synced = False
    elif breakage == "unknown_sync":
        bed.estate.synced = None
    elif breakage == "build":
        bed.estate.builds["kill-switch"] = "other"
    elif breakage == "own_build":
        kw["build_sha"] = "unknown"
    else:
        doc = bed.live()
        doc["issued_at"] = oa.format_time(T0 + 3600)
        bed.ops.write_bytes(rot.encode_doc(doc))
    before = bed.ops.read_bytes()
    code, summary = bed.rotator(**kw).run_once(now_id=KS)
    assert code == rot.EXIT_SKIPPED and summary["skip_reason"] == reason
    assert bed.ops.read_bytes() == before


@pytest.mark.parametrize("breakage", ["stale_view", "registry_error", "daemon_old",
                                      "key_file_wrong", "stale_next"])
def test_precheck_skips(bed, breakage):
    if breakage == "stale_view":
        bed.estate.services["lifecycle-manager"].frozen = b'{"format": 2}'
    elif breakage == "registry_error":
        bed.estate.services["lifecycle-manager"].frozen = b"[]x"
    elif breakage == "daemon_old":
        bed.estate.services["kill-switch"].stuck_fp = "0" * 16
    elif breakage == "key_file_wrong":
        Path(bed.identity(KS).key_path).write_text("fok_test-other-not-a-real-key\n")
    else:
        Path(bed.identity(KS).key_path + ".next").write_text("fok_test-stale-not-a-real-key\n")
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_SKIPPED and summary["skip_reason"] == "precheck", summary
    assert bed.ops.read_bytes() == before


def test_foreign_edit_is_skipped_and_classified(bed):
    assert bed.rotator().run_once(now_id=KS)[0] == 0
    bed.estate.t += rot.ESTATE_SPACING_S
    doc = bed.live()
    doc["operators"][1]["scopes"] = ["*"]
    bed.ops.write_bytes(rot.encode_doc(doc))
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_SKIPPED and summary["skip_reason"] == "foreign_edit"
    assert json.loads((bed.state / rot.STATUS_NAME).read_text())["foreign_edit"][
        "key_slots_only"] is False
    doc["operators"][1]["scopes"] = ["registry_edit"]
    doc["operators"][1]["key_not_after"] = oa.format_time(T0 + 50 * rot.DAY)
    bed.ops.write_bytes(rot.encode_doc(doc))
    code, summary = bed.rotator().run_once()
    assert summary["skip_reason"] == "foreign_edit"
    assert json.loads((bed.state / rot.STATUS_NAME).read_text())["foreign_edit"][
        "key_slots_only"] is True


def test_a_write_interrupted_before_its_status_update_is_not_a_foreign_edit(bed):
    assert bed.rotator().run_once(now_id=KS)[1]["result"] == "completed"
    assert json.loads((bed.state / rot.STATUS_NAME).read_text())["last_written_sha256"]
    bed.estate.t += rot.ESTATE_SPACING_S

    def hook(point):
        if point == "after_operators_write":
            raise Crash()
    with pytest.raises(Crash):
        bed.rotator(hook=hook).run_once(now_id="svc-registry")
    st = json.loads((bed.state / rot.STATUS_NAME).read_text())
    assert st["pending_sha256"] == rot.sha256_hex(bed.ops.read_bytes())
    assert st["last_written_sha256"] != st["pending_sha256"]
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    assert summary["operator_id"] == "svc-registry"


def test_dry_run_writes_nothing(bed):
    before = sorted(p.name for p in bed.root.rglob("*"))
    ops = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once(dry_run=True)
    assert code == 0 and summary["would"] == "rotate"
    assert bed.ops.read_bytes() == ops and bed.estate.events == []
    after = sorted(p.name for p in bed.root.rglob("*") if p.name != rot.LOCK_NAME)
    assert after == before


def test_a_journal_for_another_identity_blocks_a_forced_rotation(bed):
    assert bed.rotator(max_wait_s=0).run_once(now_id=KS)[1]["result"] == "in_progress"
    code, summary = bed.rotator().run_once(now_id="svc-registry")
    assert code == rot.EXIT_SKIPPED and summary["skip_reason"] == "lock"


def test_usage_errors(bed):
    assert bed.rotator().run_once(now_id="don")[0] == rot.EXIT_USAGE
    assert bed.rotator().run_once(now_id=KS, reason="whim")[0] == rot.EXIT_USAGE
    with pytest.raises(ValueError):
        rot.Identity(operator_id="don-breakglass", key_path="x", kind="job")
    with pytest.raises(ValueError):
        rot.Identity(operator_id="svc-killswitch", key_path="x", kind="daemon", service="nope")


# --------------------------------------------------------------------------
# format 1 -> format 2 migration (R1 review 5d, 5f)
# --------------------------------------------------------------------------

def _keygen():
    sys.path.insert(0, str(REPO / "tools"))
    import operator_keygen
    return operator_keygen


def _format1_bed(tmp_path, rows_extra=None):
    """A format 1 operators file written by the REAL operator_keygen --add-to
    (created_at in its +00:00 form)."""
    bed = Bed(tmp_path)
    kg = _keygen()
    bed.ops.unlink()
    for oid, scopes, prefixes in [("svc-killswitch", ["kill", "revive"], []),
                                  ("svc-registry", ["registry_edit"], []),
                                  (ROTATOR_ID, ["ledger_attribute"], ["keyrotation."]),
                                  ("job-provision-gb10", ["mint"], []),
                                  ("don", ["*"], []),
                                  ("don-breakglass", ["kill", "revive"], [])]:
        kg.add_entry(bed.ops, oid, sha(bed.key_values[oid]), scopes, [], prefixes)
    doc = json.loads(bed.ops.read_text())
    for r in rows_extra or []:
        doc.append(r) if isinstance(doc, list) else doc["operators"].append(r)
    if rows_extra:
        bed.ops.write_text(json.dumps(doc, indent=2) + "\n")
    return bed


def test_migration_of_a_real_keygen_written_file(tmp_path):
    bed = _format1_bed(tmp_path)
    before = json.loads(bed.ops.read_text())
    assert all(r["created_at"].endswith("+00:00") for r in before)
    oa.parse_registry_doc(before, require_active=True)     # format 1 parses today
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "migrated", summary
    after = bed.live()
    doc = oa.parse_registry_doc(after, require_active=True)
    assert doc.format == 2 and doc.generation == 1
    rows = {r["operator_id"]: r for r in after["operators"]}
    for b in before:
        r = rows[b["operator_id"]]
        assert r["created_at"] == b["created_at"][:-6] + "Z"
        assert oa.parse_time(r["created_at"]) == int(
            __import__("datetime").datetime.fromisoformat(b["created_at"]).timestamp())
        assert r["key_created_at"] == r["created_at"]
        assert r["key_sha256"] == b["key_sha256"] and "next_key" not in r
        assert r["scopes"] == b["scopes"] and r["names"] == b["names"]
    assert rows["don-breakglass"]["rotation"] == "sealed"
    assert "key_not_after" not in rows["don-breakglass"]
    assert rows["don"]["rotation"] == "remote"
    assert oa.parse_time(rows["don"]["key_not_after"]) == int(bed.estate.t) + rot.UNMANAGED_LIFETIME_S
    for i in bed.identities:
        assert rows[i.operator_id]["rotation"] == "auto"
        assert oa.parse_time(rows[i.operator_id]["key_not_after"]) == (
            int(bed.estate.t) + rot.KEY_LIFETIME_S + rot.jitter_s(i.operator_id))
    assert len({rows[i.operator_id]["key_not_after"] for i in bed.identities}) == 4  # staggered
    ev_ = bed.estate.of("keyrotation.reconciled")[0]
    assert ev_["generation"] == 1 and set(ev_["operator_ids"]) == set(rows)
    # the first rotation after the migration works
    assert bed.rotator().run_once(now_id=KS)[1]["result"] == "completed"


def test_migration_honours_the_configured_unmanaged_expiry(tmp_path):
    bed = _format1_bed(tmp_path)
    until = T0 + 120 * rot.DAY + 77
    assert bed.rotator(unmanaged_not_after=until).run_once()[0] == 0
    assert bed.row("don")["key_not_after"] == oa.format_time(until)


@pytest.mark.parametrize("extra", [
    {"operator_id": "legacy", "key_sha256": "a" * 64, "status": "active",
     "scopes": ["frobnicate"]},                                     # unknown legacy scope
    {"operator_id": "legacy", "key_sha256": "a" * 64, "status": "active", "scopes": [],
     "comment": "kept by format 1"},                                # unknown legacy field
    {"operator_id": "legacy", "key_sha256": "a" * 64, "status": "active", "scopes": [],
     "created_at": "2026-10-26T01:15:00+01:00"},                    # not the +00:00 form
])
def test_a_legacy_row_format2_refuses_blocks_the_migration_not_the_estate(tmp_path, extra):
    bed = _format1_bed(tmp_path, [extra])
    before = bed.ops.read_bytes()
    oa.parse_registry_doc(json.loads(before), require_active=True)  # format 1: still fine
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "validation", summary
    assert bed.ops.read_bytes() == before
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["reverted"] is False and failed["operator_id"] == ROTATOR_ID


def test_migration_dry_run_reports_without_writing(tmp_path):
    bed = _format1_bed(tmp_path)
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once(dry_run=True)
    assert code == 0 and summary["would"] == "migrate"
    assert bed.ops.read_bytes() == before and bed.estate.events == []


def test_normalise_created_at():
    assert rot.normalise_created_at("2026-10-26T01:15:00+00:00") == "2026-10-26T01:15:00Z"
    assert rot.normalise_created_at("2026-10-26T01:15:00Z") == "2026-10-26T01:15:00Z"
    for v in ("2026-10-26T01:15:00+01:00", "2026-10-26T01:15:00.5+00:00", "x+00:00", 7, None):
        assert rot.normalise_created_at(v) == v



# --------------------------------------------------------------------------
# defence in depth: umask, the installed parser, the frozen event schema
# --------------------------------------------------------------------------

def test_the_run_sets_umask_077_and_restores_it(bed, monkeypatch):
    calls = []
    real = os.umask

    def recording(mask):
        calls.append(mask)
        return real(mask)
    monkeypatch.setattr(rot.os, "umask", recording)
    assert bed.rotator().run_once(now_id=KS)[0] == 0
    assert calls[0] == 0o077 and len(calls) == 2


@pytest.mark.skipif(os.name != "posix", reason="POSIX umask")
def test_the_whole_run_runs_under_umask_077(bed):
    seen = []

    def hook(point):
        cur = os.umask(0)
        os.umask(cur)
        seen.append(cur)
    before = os.umask(0)
    os.umask(before)
    assert bed.rotator(hook=hook).run_once(now_id=KS)[0] == 0
    assert seen and all(m == 0o077 for m in seen)
    after = os.umask(0)
    os.umask(after)
    assert after == before


def test_a_candidate_the_installed_parser_refuses_is_never_written(bed, monkeypatch):
    """A NEXT key whose hash is already listed (here: don's) passes diff_guard
    (key fields of the target only) but the R1 parser refuses a hash that
    appears twice; the rotator must not write it."""
    monkeypatch.setattr(rot, "generate_key", lambda: bed.key_values["don"])
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "validation", summary
    assert bed.ops.read_bytes() == before
    assert not Path(bed.identity(KS).key_path + ".next").exists()
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["phase"] == "publish" and failed["reverted"] is False


def test_every_event_is_validated_before_it_is_appended(bed):
    appended = []
    bed.estate.append = lambda t, p: appended.append((t, p))
    r = bed.rotator()
    with pytest.raises(Exception):
        r._emit("keyrotation.skipped", {"operator_id": None, "estate": "gb10",
                                         "run_id": "r1", "reason": "lock"})
    with pytest.raises(Exception):
        r._emit("keyrotation.cutover", {"operator_id": KS, "estate": "gb10", "run_id": "r1",
                                         "new_fp": "a" * 64})
    assert appended == []


def test_a_candidate_diff_guard_refuses_is_never_written(bed, monkeypatch):
    """The write path runs diff_guard before anything is written: a candidate
    that changes a scope (here injected into the header step) is refused,
    ledgered as reason_class policy, and the file is untouched."""
    real = rot.Rotator._header

    def header(self, doc, generation):
        out = real(self, doc, generation)
        out["operators"] = [dict(r) for r in out["operators"]]
        out["operators"][0]["scopes"] = ["*"]
        return out
    monkeypatch.setattr(rot.Rotator, "_header", header)
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "policy", summary
    assert bed.ops.read_bytes() == before
    assert bed.estate.of("keyrotation.failed")[0]["reason_class"] == "policy"


def test_an_event_ledgered_and_journaled_before_a_crash_is_not_ledgered_again(bed):
    """The journal records every once-per-run event it appended; a crash right
    after the cutover was ledgered (still in CONFIRM-SWITCH) must not ledger
    it twice when the next run resumes that phase."""
    real_append, real_now = bed.estate.append, bed.estate.now
    armed = {"crash": False, "done": False}

    def append(event_type, payload):
        out = real_append(event_type, payload)
        if event_type == "keyrotation.cutover" and not armed["done"]:
            armed["crash"] = True
        return out

    def now():
        if armed["crash"]:
            armed["crash"], armed["done"] = False, True
            raise Crash()
        return real_now()
    bed.estate.append, bed.estate.now = append, now
    with pytest.raises(Crash):
        bed.rotator().run_once(now_id=KS)
    assert json.loads((bed.state / f"journal-{KS}.json").read_text())["phase"] == "confirm_switch"
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    assert bed.estate.types().count("keyrotation.cutover") == 1
