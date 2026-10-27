"""phase_g_check check 5 ("collateral") and the C-6 ledger observer (review of PR #42, M1).

The observer (switched on by this PR) writes ``operator.mode_changed`` /
``operator.registry_changed`` with no agent id at the first observation of each
service and on every change; one lands inside a Stage 1 audit window whenever the
audit starts soon after a flip, a recreate or a ledger restart. Check 5 must not call
that collateral (a false RED), must print it as an [INFO] line (never drop it
silently), and must exempt ONLY those two exact types with no agent id, so it can
never mask a real collateral event.

These run the real ``collateral()`` over a fixed ledger tail (``ep._ledger`` is
replaced); the estate-backed collateral tests live in test_phase_g_check.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import estate_probe as ep  # noqa: E402
import phase_g_check as pgc  # noqa: E402

CANARY = "canary-gb10"


def _obs(etype, service, **extra):
    payload = {"service": service, "mode": "log-only", "previous_mode": "off", "startup": False,
               "observed_from": "health"}
    return {"event_type": etype, "agent_id": None, "payload": payload, **extra}


class _Ctx:
    agent = CANARY
    estate = object()


@pytest.fixture()
def run_check(monkeypatch, capsys):
    def go(tail, allow=frozenset()):
        head = [{"event_type": "registry.registered", "agent_id": "before-the-start"}]
        monkeypatch.setattr(ep, "_ledger", lambda estate: head + tail)
        monkeypatch.setattr(ep, "RESULTS", [])
        pgc.collateral(_Ctx(), len(head), set(allow))
        out = capsys.readouterr().out
        return [label for ok, label in ep.RESULTS if not ok], out
    return go


CANARY_ROWS = [{"event_type": "kill.revive", "agent_id": CANARY, "payload": {}},
               {"event_type": "operator.unauthenticated", "agent_id": None, "payload": {}}]


def test_observer_rows_in_the_window_pass_and_are_printed_as_info(run_check):
    tail = [*CANARY_ROWS, _obs("operator.mode_changed", "kill-switch"),
            _obs("operator.registry_changed", "kill-switch"), _obs("operator.registry_changed", "agent-registry")]
    failed, out = run_check(tail)
    assert failed == [], out
    assert "[PASS] no ledger events about a non-canary agent since the start" in out
    assert ("[INFO] 1 x operator.mode_changed with no agent id (C-6 ledger observer: kill-switch)"
            in out), out
    assert ("[INFO] 2 x operator.registry_changed with no agent id (C-6 ledger observer: agent-registry, "
            "kill-switch)" in out), out


@pytest.mark.parametrize("real", [
    {"event_type": "bystander.touched", "agent_id": "agent-bystander", "payload": {}},
    {"event_type": "bystander.touched", "agent_id": "canary-fly", "payload": {}},
    {"event_type": "debug.note", "agent_id": None, "payload": {}},                 # no agent id, other type
    {"event_type": "operator.mode_changed", "agent_id": "agent-bystander",         # observer type WITH an agent
     "payload": {"service": "kill-switch"}},
    {"event_type": "operator.mode_changed", "agent_id": "", "payload": {}},       # empty, not None
    {"event_type": "operator.mode_changed ", "agent_id": None, "payload": {}},    # not the exact type
])
def test_a_real_collateral_event_next_to_observer_rows_is_still_red(run_check, real):
    tail = [*CANARY_ROWS, _obs("operator.mode_changed", "kill-switch"), real,
            _obs("operator.registry_changed", "kill-switch")]
    failed, out = run_check(tail)
    agent = real["agent_id"] or "<none>"
    assert failed and any(f"x {real['event_type']} for {agent}" in f and "NOT intended" in f for f in failed), out
    assert "[INFO] 1 x operator.mode_changed with no agent id" in out          # still reported, never dropped


def test_an_unreadable_service_name_is_shown_as_a_question_mark(run_check):
    failed, out = run_check([_obs("operator.mode_changed", "fok_" + "x" * 40), _obs("operator.mode_changed", None)])
    assert failed == [] and "C-6 ledger observer: ?)" in out and "fok_" not in out, out
