"""Key rotation slice R4a, fix round after the independent review (kr-r4a
review, verdict NO-SHIP at 817968e). Pins:

* F1 / F2 (HIGH): a failure at or after PROMOTE is never key-restoring. The
  journal goes back to ``promote`` (outside BEFORE_PROMOTE), so the 24 h
  abort never runs against a promoted or both-keys registry; and ``_abort``
  acts on LIVE state (restores ``<key>.prev`` only when the live current hash
  is its hash, removes ``next_key`` by editing the live document, refuses
  when the live current slot holds the new key). Both review reproductions
  are here, plus tests that kill the "post-PROMOTE phase back to soak" and
  "abort re-publishes .prev" mutants.
* F3 / ruling 2: written-but-unseen PUBLISH / PROMOTE / migration writes are
  ledgered before the failure.
* ruling 7: a migration that hits ``registry_error`` writes the exact
  pre-migration bytes back.
* F4: the self CONFIRM-SWITCH proof whenever the operator mode is not off.
* F5: stray SWITCH hard links are swept.
* F6: an unreadable journal halts with an alert.
* ruling 6 (second half): an aborted incident rotation restores the
  original expiry.

Every key is a fake test value made in a temp directory."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rotation_fakes_r4a import T0, Bed, sha  # noqa: E402

from field_core import operator_auth as oa  # noqa: E402
from field_core import rotation as rot  # noqa: E402

KS = "svc-killswitch"
HOUR = 3600


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


def _answers(bed, oid, key_sha):
    return {svc: s.verify_hash(oid, key_sha) for svc, s in bed.estate.services.items()}


def _journal(bed, oid=KS):
    p = bed.state / f"journal-{oid}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _never_current_for_new_key(bed, old_sha, svc="federation-broker", on_first=None):
    """One service never answers ``current`` for the new key (the review's
    single fault: a service that is down gives the same result)."""
    seen = {"n": 0}

    def lie(oid, key_sha, ans):
        if oid == KS and key_sha != old_sha and ans["matched"] == "current":
            seen["n"] += 1
            if seen["n"] == 1 and on_first is not None:
                on_first()
            return {**ans, "matched": "none", "matchable_now": False}
        return ans
    bed.estate.services[svc].answer_hook = lie
    return seen


# --------------------------------------------------------------------------
# F1 (single fault): the 24 h abort never runs after a post-PROMOTE revert
# --------------------------------------------------------------------------

def test_repro_F1_post_promote_revert_is_never_aborted_and_never_locks_out(bed):
    old_sha = bed.key_sha(KS)
    _never_current_for_new_key(bed, old_sha)
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["phase"] == "verify_current", summary
    new_sha = bed.key_sha(KS)
    assert new_sha != old_sha
    assert _journal(bed)["phase"] == rot.POST_PROMOTE_RETRY == "promote"
    # hourly runs past the 24 h limit: promote, 9b fails, revert; never abort
    for _ in range(3):
        bed.estate.t += 9 * HOUR
        code, summary = bed.rotator().run_once()
        assert code == rot.EXIT_FAILED and summary["phase"] == "verify_current", summary
        assert _journal(bed)["phase"] == "promote"
    assert bed.estate.t >= T0 + rot.INFLIGHT_LIMIT_S
    assert "keyrotation.aborted" not in bed.estate.types()
    # the daemon keeps the new key; the registry holds both keys, both valid
    assert bed.key_sha(KS) == new_sha
    row = bed.row(KS)
    assert row["key_sha256"] == old_sha and row["next_key"]["key_sha256"] == new_sha
    assert rot.key_file_sha(Path(bed.identity(KS).key_path + ".prev")) == old_sha
    for ans in _answers(bed, KS, new_sha).values():
        assert ans["matched"] == "next" and ans["matchable_now"] and not ans["retired"]
    # past the OLD key's expiry the new key still authenticates (NEXT slot)
    bed.estate.t = T0 + 40 * rot.DAY
    code, summary = bed.rotator().run_once()
    assert summary["phase"] == "verify_current" and "keyrotation.aborted" not in bed.estate.types()
    assert bed.key_sha(KS) == new_sha
    for ans in _answers(bed, KS, new_sha).values():
        assert ans["matched"] == "next" and ans["matchable_now"] and not ans["retired"]
    # the fault clears: the next run completes the rotation
    bed.estate.services["federation-broker"].answer_hook = None
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_OK and summary["result"] == "completed", summary
    assert bed.row(KS)["key_sha256"] == new_sha and "next_key" not in bed.row(KS)
    for ans in _answers(bed, KS, new_sha).values():
        assert ans["matched"] == "current" and ans["matchable_now"]


def test_promote_not_seen_resumes_at_promote_not_soak(bed):
    """PROMOTE not seen by one service: revert, journal at ``promote``; 25 h
    later the next run promotes again (no abort)."""
    old_sha = bed.key_sha(KS)
    frozen = {"on": True}

    def hook(point):
        if point == "before_operators_write" and bed.estate.of("keyrotation.cutover") \
                and frozen["on"] and not bed.estate.of("keyrotation.failed"):
            bed.estate.services["ops-console"].frozen = bed.ops.read_bytes()
    code, _ = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    assert _journal(bed)["phase"] == "promote"
    new_sha = bed.key_sha(KS)
    bed.estate.services["ops-console"].frozen = None
    frozen["on"] = False
    bed.estate.t += rot.INFLIGHT_LIMIT_S + HOUR
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_OK and summary["result"] == "completed", summary
    assert "keyrotation.aborted" not in bed.estate.types()
    assert bed.row(KS)["key_sha256"] == new_sha != old_sha


# --------------------------------------------------------------------------
# F2 (double fault): 9b fails and its revert cannot be written
# --------------------------------------------------------------------------

def test_repro_F2_unwritten_revert_after_promote_never_restores_the_old_key(bed):
    old_sha = bed.key_sha(KS)

    def break_prev():
        (bed.state / rot.PREV_NAME).write_bytes(b"{not json")
    _never_current_for_new_key(bed, old_sha, on_first=break_prev)
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["reverted"] is False, summary
    new_sha = bed.key_sha(KS)
    row = bed.row(KS)
    assert row["key_sha256"] == new_sha and "next_key" not in row       # still promoted
    assert _journal(bed)["phase"] == "promote"
    bed.estate.t += rot.INFLIGHT_LIMIT_S + HOUR
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["phase"] == "verify_current", summary
    assert "keyrotation.aborted" not in bed.estate.types()
    assert bed.key_sha(KS) == new_sha                    # the key file was NOT restored
    assert bed.row(KS)["key_sha256"] == new_sha
    for svc, ans in _answers(bed, KS, new_sha).items():
        if svc != "federation-broker":
            assert ans["matched"] == "current" and ans["matchable_now"], svc
    bed.estate.services["federation-broker"].answer_hook = None
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_OK and summary["result"] == "completed", summary
    assert not Path(bed.identity(KS).key_path + ".prev").exists()


# --------------------------------------------------------------------------
# fix (b): _abort acts on live state (journals from an older build, or bugs)
# --------------------------------------------------------------------------

def test_abort_removes_next_key_from_the_live_document_not_from_a_both_keys_prev(bed):
    """The review's F1 end state reached through a journal left in ``soak``
    (as the reviewed build wrote it): the abort must restore the old key file
    (it IS the live current key) and remove ``next_key`` from the LIVE
    document. Re-publishing the both-keys ``.prev`` would keep ``next_key``
    for a destroyed key and PRECHECK would refuse the identity for ever."""
    old_sha = bed.key_sha(KS)
    _never_current_for_new_key(bed, old_sha)
    bed.rotator().run_once(now_id=KS)
    new_sha = bed.key_sha(KS)
    prev_doc = json.loads((bed.state / rot.PREV_NAME).read_text())
    prev_row = next(r for r in prev_doc["operators"] if r["operator_id"] == KS)
    assert prev_row["next_key"]["key_sha256"] == new_sha        # .prev holds both keys
    j = _journal(bed)
    j["phase"] = "soak"
    (bed.state / f"journal-{KS}.json").write_text(json.dumps(j))
    bed.estate.t += rot.INFLIGHT_LIMIT_S + HOUR
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["result"] == "aborted", summary
    aborted = bed.estate.of("keyrotation.aborted")[-1]
    assert aborted["reason_class"] == "timeout" and aborted["reverted"] is True
    assert bed.key_sha(KS) == old_sha
    row = bed.row(KS)
    assert row["key_sha256"] == old_sha and "next_key" not in row
    kp = bed.identity(KS).key_path
    assert not Path(kp + ".next").exists() and not Path(kp + ".prev").exists()
    assert _journal(bed) is None
    # the identity is rotatable again (no lock-out)
    bed.estate.services["federation-broker"].answer_hook = None
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_OK and summary["result"] == "completed", summary


def test_abort_refuses_when_the_live_current_slot_holds_the_new_key(bed):
    old_sha = bed.key_sha(KS)

    def break_prev():
        (bed.state / rot.PREV_NAME).write_bytes(b"{not json")
    _never_current_for_new_key(bed, old_sha, on_first=break_prev)
    bed.rotator().run_once(now_id=KS)
    new_sha = bed.key_sha(KS)
    j = _journal(bed)
    j["phase"] = "soak"
    (bed.state / f"journal-{KS}.json").write_text(json.dumps(j))
    before = bed.ops.read_bytes()
    bed.estate.t += rot.INFLIGHT_LIMIT_S + HOUR
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["result"] == "failed", summary
    assert summary["reason_class"] == "internal"
    assert "keyrotation.aborted" not in bed.estate.types()
    failed = bed.estate.of("keyrotation.failed")[-1]
    assert failed["reason_class"] == "internal" and failed["reverted"] is False
    assert bed.key_sha(KS) == new_sha and bed.ops.read_bytes() == before
    assert rot.key_file_sha(Path(bed.identity(KS).key_path + ".prev")) == old_sha
    assert _journal(bed)["phase"] == "promote"            # forward only from here
    bed.estate.services["federation-broker"].answer_hook = None
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_OK and summary["result"] == "completed", summary


def test_abort_keeps_a_key_prev_that_is_not_the_live_current_key(bed):
    """A ``<key>.prev`` whose hash is not the live current hash is never put
    back over the key file."""
    old_sha = bed.key_sha(KS)
    code, _ = bed.rotator(max_wait_s=0).run_once(now_id=KS)       # in the soak
    new_sha = bed.key_sha(KS)
    live = bed.live()
    row = next(r for r in live["operators"] if r["operator_id"] == KS)
    row["key_sha256"] = sha("fok_test-someone-else-not-a-real-key")
    bed.ops.write_bytes(rot.encode_doc(live))
    st = json.loads((bed.state / rot.STATUS_NAME).read_text())
    st["last_written_sha256"] = rot.sha256_hex(bed.ops.read_bytes())
    (bed.state / rot.STATUS_NAME).write_text(json.dumps(st))
    bed.estate.t += rot.INFLIGHT_LIMIT_S + HOUR
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "internal", summary
    assert bed.key_sha(KS) == new_sha
    assert rot.key_file_sha(Path(bed.identity(KS).key_path + ".prev")) == old_sha


def test_aborted_incident_rotation_restores_the_original_expiry(bed):
    original = bed.row(KS)["key_not_after"]
    bed.estate.services["kill-switch"].stuck_fp = bed.key_sha(KS)[:16]
    code, summary = bed.rotator().run_once(now_id=KS, reason="incident")
    assert code == rot.EXIT_FAILED and summary["result"] == "aborted", summary
    row = bed.row(KS)
    assert "next_key" not in row and row["key_not_after"] == original


# --------------------------------------------------------------------------
# F3 / ruling 2 / ruling 7: every written generation is ledgered
# --------------------------------------------------------------------------

def test_publish_not_seen_ledgers_the_published_generation_before_the_revert(bed):
    bed.estate.services["spend-governor"].frozen = bed.ops.read_bytes()
    code, _ = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    types = bed.estate.types()
    assert types.index("keyrotation.published") < types.index("keyrotation.failed")
    pub = bed.estate.of("keyrotation.published")[0]
    failed = bed.estate.of("keyrotation.failed")[0]
    assert pub["generation"] == 11 and failed["generation"] == 12


def test_promote_not_seen_ledgers_the_promoted_generation_before_the_revert(bed):
    def hook(point):
        if point == "before_operators_write" and bed.estate.of("keyrotation.cutover") \
                and not bed.estate.of("keyrotation.failed"):
            bed.estate.services["ops-console"].frozen = bed.ops.read_bytes()
    code, _ = bed.rotator(hook=hook).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    types = bed.estate.types()
    assert types.index("keyrotation.retired") < types.index("keyrotation.failed")
    ret = bed.estate.of("keyrotation.retired")[0]
    failed = bed.estate.of("keyrotation.failed")[0]
    assert ret["generation"] == 12 and failed["generation"] == 13


def _format1_bed(tmp_path):
    from test_rotation_r4a import _format1_bed as make
    return make(tmp_path)


def test_migration_registry_error_restores_the_exact_format1_bytes(tmp_path):
    bed = _format1_bed(tmp_path)
    original = bed.ops.read_bytes()

    def hook(point):
        if point == "after_operators_write":
            bed.estate.services["kill-switch"].force_error = "operator registry malformed"
    code, summary = bed.rotator(hook=hook).run_once()
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "registry_error", summary
    assert bed.ops.read_bytes() == original
    rec = bed.estate.of("keyrotation.reconciled")[0]
    failed = bed.estate.of("keyrotation.failed")[0]
    types = bed.estate.types()
    assert types.index("keyrotation.reconciled") < types.index("keyrotation.failed")
    assert rec["generation"] == 1
    assert failed["reverted"] is True and failed["generation"] == 1
    assert failed["registry_sha16"] == rot.sha256_hex(original)[:16]
    # format 1 after a seen format 2: every key still current on all eight
    bed.estate.services["kill-switch"].force_error = None
    for oid in ("svc-killswitch", "don", "don-breakglass"):
        for ans in _answers(bed, oid, sha(bed.key_values[oid])).values():
            assert ans["matched"] == "current" and ans["matchable_now"], oid
    # not a foreign edit: the next run migrates again, above the high-water mark
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_OK and summary["result"] == "migrated", summary
    assert bed.live()["generation"] == 2


def test_migration_not_seen_is_ledgered_as_reconciled_then_failed_and_kept(tmp_path):
    bed = _format1_bed(tmp_path)
    bed.estate.services["spend-governor"].frozen = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "publish_not_seen"
    rec = bed.estate.of("keyrotation.reconciled")[0]
    failed = bed.estate.of("keyrotation.failed")[0]
    assert rec["generation"] == 1 == bed.live()["generation"]
    assert rec["registry_sha16"] == rot.sha256_hex(bed.ops.read_bytes())[:16]
    assert failed["reverted"] is False and failed["generation"] is None


# --------------------------------------------------------------------------
# F4, F5, F6
# --------------------------------------------------------------------------

def test_self_cutover_without_an_authenticated_fp_aborts_when_mode_is_not_off(bed):
    oid = "svc-rotator-gb10"
    old = bed.key_sha(oid)
    bed.estate.self_key = None                # the append did not authenticate
    code, summary = bed.rotator().run_once(now_id=oid)
    assert code == rot.EXIT_FAILED and summary["result"] == "aborted", summary
    assert summary["reason_class"] == "switch_not_seen"
    assert bed.key_sha(oid) == old and "next_key" not in bed.row(oid)


def test_self_cutover_proof_is_not_required_when_mode_is_off(bed):
    oid = "svc-rotator-gb10"
    bed.estate.self_key = None
    bed.estate.operator_mode = oa.OFF
    code, summary = bed.rotator().run_once(now_id=oid)
    assert code == rot.EXIT_OK and summary["result"] == "completed", summary


def test_stray_switch_links_are_swept(bed):
    kp = Path(bed.identity(KS).key_path)
    stray = kp.with_name(f".{kp.name}.deadbeef.link")
    os.link(str(kp), str(stray))
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_OK, summary
    assert not list(kp.parent.glob(f".{kp.name}.*.link"))


def test_an_unreadable_journal_halts_with_an_alert(bed):
    (bed.state / "journal-svc-registry.json").write_text("{not json")
    before = bed.ops.read_bytes()
    code, summary = bed.rotator().run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "internal", summary
    assert bed.ops.read_bytes() == before
    assert not Path(bed.identity(KS).key_path + ".next").exists()
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["operator_id"] == "svc-registry" and failed["phase"] == "precheck"
    assert "keyrotation.started" not in bed.estate.types()
    code, summary = bed.rotator().run_once(dry_run=True)
    assert code == rot.EXIT_FAILED
