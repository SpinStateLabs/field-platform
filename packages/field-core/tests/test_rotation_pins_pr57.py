"""Pins for the mutants that survived the PR 57 review (ssl-ff-reviewer-4, head 30ac1e11, findings F-R4a-2 and F-R4a-3):
V3 (the failed event's ``reverted`` must say whether the revert really happened), P1 (the retry cap constant), P5a and P5b
(the post-PROMOTE failure counter on the two paths the earlier cap test did not drive: a promote the services do not see,
and a promote the diff guard refuses on a retry), P7 (the retired event is ledgered again when the retry succeeds).
Every key is a fake test value made in a temp directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rotation_fakes_r4a import Bed  # noqa: E402

from field_core import operator_auth as oa  # noqa: E402
from field_core import rotation as rot  # noqa: E402

KS = "svc-killswitch"


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


def _journal(bed) -> rot.Journal:
    return rot.Journal.from_bytes((bed.state / f"journal-{KS}.json").read_bytes())


def _freeze_hook(bed, *, drop_prev=False):
    """Make ops-console keep serving the pre-PROMOTE file, so the promoted file is never seen by every service. With
    ``drop_prev`` the saved pre-publish copy is deleted right after the promote, so the auto-revert cannot be written."""
    state = {"pre": None}

    def hook(point):
        if point == "before_operators_write" and bed.estate.of("keyrotation.cutover") and state["pre"] is None:
            state["pre"] = bed.ops.read_bytes()
            bed.estate.services["ops-console"].frozen = state["pre"]
        if point == "after_promote" and drop_prev:
            (bed.state / rot.PREV_NAME).unlink()
    return hook


def test_P1_the_post_promote_retry_cap_is_ten():
    assert rot.POST_PROMOTE_MAX_FAILURES == 10


def test_P5a_a_promote_the_services_do_not_see_counts_one_post_promote_failure(bed):
    code, summary = bed.rotator(hook=_freeze_hook(bed)).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["phase"] == "promote" and summary["reverted"] is True, summary
    j = _journal(bed)
    assert j.phase == rot.POST_PROMOTE_RETRY and j.post_promote_failures == 1


def test_V3_a_revert_that_could_not_be_written_is_not_ledgered_as_reverted(bed):
    code, summary = bed.rotator(hook=_freeze_hook(bed, drop_prev=True)).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and summary["phase"] == "promote", summary
    assert summary["reverted"] is False and summary["generation"] is None
    failed = bed.estate.of("keyrotation.failed")[0]
    assert failed["phase"] == "promote" and failed["reverted"] is False and failed["generation"] is None
    assert failed["registry_sha16"] is None
    assert _journal(bed).post_promote_failures == 1          # still counted as a post-PROMOTE failure


def test_P5b_a_promote_the_diff_guard_refuses_on_a_retry_counts_a_failure(bed, monkeypatch):
    code, _ = bed.rotator(hook=_freeze_hook(bed)).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED and _journal(bed).post_promote_failures == 1
    bed.estate.services["ops-console"].frozen = None
    real = rot.Rotator._header

    def header(self, doc, generation):
        out = real(self, doc, generation)
        out["operators"] = [dict(r) for r in out["operators"]]
        out["operators"][0]["scopes"] = ["*"]                # the diff guard must refuse this
        return out
    monkeypatch.setattr(rot.Rotator, "_header", header)
    code, summary = bed.rotator().run_once()
    assert code == rot.EXIT_FAILED and summary["reason_class"] == "policy", summary
    assert _journal(bed).post_promote_failures == 2          # _fail_kept counts it (phase is already after PROMOTE)
    assert bed.estate.of("keyrotation.failed")[-1]["reason_class"] == "policy"


def test_P7_the_retired_event_is_ledgered_again_when_the_retry_succeeds(bed):
    code, _ = bed.rotator(hook=_freeze_hook(bed)).run_once(now_id=KS)
    assert code == rot.EXIT_FAILED
    first = len(bed.estate.of("keyrotation.retired"))
    bed.estate.services["ops-console"].frozen = None
    code, summary = bed.rotator().run_once()
    assert code == 0 and summary["result"] == "completed", summary
    assert len(bed.estate.of("keyrotation.retired")) == first + 1
