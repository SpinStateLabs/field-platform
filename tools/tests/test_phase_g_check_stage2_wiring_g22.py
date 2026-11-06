"""G22 condition C1 (reviewer R-PR827-f129b1e, mutant S4): `phase_g_check --stage 2` really runs the Stage 2 entry check.

The G22 suite calls `stage2_precondition` directly; none of it goes through `main`. If the call in `_run` were removed,
the flag would still parse and silently check nothing, which is the fail-open shape for the gate that stops Stage 2.
These tests drive `main(["--stage", "2", ...])` against a fake estate (no network, no service) and look at the exit
status and the printed line. Throwaway constants only.
"""
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import estate_probe as ep  # noqa: E402
import phase_g_check as pgc  # noqa: E402

LINE = "internal secret hash present on kill-switch and registry /health"


class FakeEstate:
    """Answers only what `_run` reads before mode detection; records every call."""
    healths: dict = {}
    calls: list = []

    def __init__(self, base, secret):
        pass

    def call(self, method, path, auth=True, **kw):
        type(self).calls.append((method, path))
        if path == "/ledger/health":
            return 200, {"event_count": 0}
        answer = type(self).healths.get(path)
        return (200, answer) if answer is not None else (503, {})


@pytest.fixture
def drive(monkeypatch):
    def go(killswitch: bool, registry: bool, *stage: str):
        FakeEstate.calls = []
        FakeEstate.healths = {"/killswitch/health": {"internal_secret_sha256_present": killswitch},
                              "/registry/health": {"internal_secret_sha256_present": registry}}
        monkeypatch.setattr(pgc.ep, "Estate", FakeEstate)
        monkeypatch.setattr(pgc.ep, "_require_canary", lambda estate, agent: None)
        monkeypatch.setattr(pgc.ep, "_heartbeat_killed", lambda estate, agent: False)
        monkeypatch.setattr(pgc, "detect_mode", lambda ctx, expect: None)   # stop after the entry check
        monkeypatch.setattr(pgc, "_settle_canary", lambda ctx: False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = pgc.main(["--base", "http://127.0.0.1:9", *stage])
        return code, out.getvalue()
    return go


def test_stage_2_fails_through_main_when_the_hash_is_missing(drive):
    code, out = drive(True, False, "--stage", "2")
    assert code != 0
    assert f"[FAIL] {LINE} (1 of 2)" in out
    assert ("GET", "/killswitch/health") in FakeEstate.calls and ("GET", "/registry/health") in FakeEstate.calls


def test_stage_2_fails_through_main_when_neither_has_the_hash(drive):
    code, out = drive(False, False, "--stage", "2")
    assert code != 0
    assert f"[FAIL] {LINE} (0 of 2)" in out


def test_stage_2_line_passes_through_main_when_both_have_the_hash(drive):
    _, out = drive(True, True, "--stage", "2")
    assert f"[PASS] {LINE} (2 of 2)" in out
    assert "[FAIL]" not in out.split(LINE)[0]


def test_without_the_stage_flag_the_entry_check_does_not_run(drive):
    _, out = drive(False, False)
    assert LINE not in out
    assert not any(p in ("/killswitch/health", "/registry/health") for _, p in FakeEstate.calls)
