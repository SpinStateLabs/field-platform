#!/usr/bin/env python3
"""stage2_driver - the ``Actions`` driver for Stage 2 (kill-switch only under REQUIRE) of ``stage_controller``.

WHAT IT IS. ``stage_controller.Controller.run(2, live=True)`` needs an ``Actions`` object (``stage_controller.py``
module docstring: "the coordinator's driver"; none ships there). This is that driver for Stage 2 only, with the estate
I/O behind a small ``Stage2Estate`` protocol the coordinator supplies on the host that holds the compose files and the
override file. This module contains no estate address, no command line, no key and no flag value, and it has no command
line of its own: nothing here touches an estate unless a caller hands it a ``Stage2Estate``.

THE NATIVE PATH. Only ``Controller.run`` writes ``stage_start`` / ``step_done`` / ``stage_done``, and the
``stage_controller`` CLI deliberately has no ``run``. ``run_stage2`` is the one entry point:

  1. The G22 gate record and the alerts record must already be in the records file, bound to the build sha
     (``python tools/stage_controller.py record gate G22 --build-sha SHA``; ``record alerts-proven --build-sha SHA``).
     This module writes neither.
  2. The Stage 2 go sentence is passed in as an argument (G25). It is Don's: this module never reads, builds or
     defaults one.
  3. Pre-flight: if the estate is ALREADY armed (the override file exists) the run is ``Refused("stage2_already_armed")``
     before the controller is even built, because ``Controller.run(2)`` re-executes ``write_override`` and
     ``recreate_killswitch``, and any abort rolls back with ``delete_override`` + ``recreate_killswitch``: on an armed
     Stage 2 that disarms it. ``allow_already_armed=True`` is the explicit, narrower alternative: the driver then takes a
     snapshot and treats the arming steps as no-ops and the rollback steps as no-ops, so an abort never disarms what was
     armed before the run (the rollback verification then expects ``enforce``, not ``log-only``).
  4. ``live=False`` (the default) is the controller's dry run: no action runs, a ``plan`` record is written.

STEP MEANINGS (runbook ``docs/runbooks/v1.2-deploy-rollback.md``, "Stage 2, kill-switch only under REQUIRE"):
``write_override`` = write the uncommitted override file (step 4); ``recreate_killswitch`` = ``up`` the kill-switch alone
(step 5, with the override file in the project; on rollback, step 8, without it); ``delete_override`` = step 8. The
driver decides "with or without the override" from the estate (``override_present``), never from a flag, so the forward
and rollback uses of the same step name cannot be mixed up.

CHECKS. After ``write_override`` the override must be present. After ``recreate_killswitch`` the mode must read
``enforce`` when the override is in place and ``log-only`` when it is not (``phase_g_check --expect-mode``), and the
services must be healthy. ``rollback_verify`` expects ``log-only`` and no override on a fresh run, and ``enforce`` with
the override still present on an ``allow_already_armed`` run. A check that cannot be answered is a failure (fail closed).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Mapping, Protocol, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stage_controller as sc  # noqa: E402

STAGE = 2
REFUSE_ARMED = "stage2_already_armed"


class Stage2Estate(Protocol):
    """The estate I/O the coordinator supplies. Every method acts on one estate. A raise is a failure of that call."""

    def override_present(self) -> bool:
        """True when the uncommitted Stage 2 override file exists."""

    def write_override(self) -> None:
        """Write the override file (runbook Stage 2 step 4)."""

    def delete_override(self) -> None:
        """Delete the override file (runbook Stage 2 step 8)."""

    def recreate_kill_switch(self, with_override: bool) -> None:
        """``up`` the kill-switch alone: with the override file in the project when ``with_override``, without otherwise."""

    def mode(self) -> str:
        """The kill-switch REQUIRE mode ``phase_g_check --expect-mode`` reports: ``enforce`` or ``log-only``."""

    def healthy(self) -> bool:
        """True when every service answers /health."""

    def counters(self) -> Mapping[str, Mapping[str, int]]:
        """Per service ``dropped_unauthenticated_records`` and ``dropped_refused_records`` from its /health."""


class Stage2Actions:
    """``stage_controller.Actions`` for Stage 2 over a ``Stage2Estate``."""

    def __init__(self, estate: Stage2Estate, *, armed_before: bool = False):
        self.estate = estate
        #: True when the estate was already armed at the start of the run (``allow_already_armed``): arming and rollback
        #: steps are then no-ops, so nothing this run does or aborts can disarm it
        self.armed_before = armed_before

    def counters(self) -> Mapping[str, Mapping[str, int]]:
        return self.estate.counters()

    def do(self, stage: int, step: str) -> None:
        if stage != STAGE:
            raise ValueError("stage2 driver runs stage 2 only")
        if self.armed_before and step in ("write_override", "delete_override", "recreate_killswitch"):
            return                                   # already armed: change nothing, in either direction
        if step == "write_override":
            self.estate.write_override()
        elif step == "delete_override":
            self.estate.delete_override()
        elif step == "recreate_killswitch":
            self.estate.recreate_kill_switch(with_override=self.estate.override_present())
        else:
            raise ValueError("unknown stage 2 step")

    def check(self, stage: int, step: str) -> Sequence[str]:
        if stage != STAGE:
            return [sc.Abort.CONTROLLER_ERROR.value]
        failed: list[str] = []
        try:
            present = self.estate.override_present()
            if step == "write_override":
                if not present:
                    failed.append(sc.Abort.CHECKLIST_ITEM.value)
            elif step == "recreate_killswitch":
                if self.estate.mode() != ("enforce" if present else "log-only"):
                    failed.append(sc.Abort.PHASE_G_CHECK.value)
                if not self.estate.healthy():
                    failed.append(sc.Abort.HEALTH.value)
            elif step == "rollback_verify":
                expect_armed = self.armed_before
                if present != expect_armed or self.estate.mode() != ("enforce" if expect_armed else "log-only"):
                    failed.append(sc.Abort.PHASE_G_CHECK.value)
                if not self.estate.healthy():
                    failed.append(sc.Abort.HEALTH.value)
            else:
                failed.append(sc.Abort.CONTROLLER_ERROR.value)
        except Exception:                            # a check that cannot answer is a failed check
            failed.append(sc.Abort.CONTROLLER_ERROR.value)
        return failed


def run_stage2(records: "sc.Records", estate: Stage2Estate, *, go_sentence: Any, build_sha: str,
               expected_services: Sequence[str], live: bool = False, allow_already_armed: bool = False,
               alert_estate: str | None = None, env: Mapping[str, str] | None = None) -> "sc.Result":
    """Run Stage 2 through ``Controller.run``. ``Refused`` (a fixed token, one ``refused`` record) when a precondition is
    missing, and ``Refused("stage2_already_armed")`` when the estate is armed and ``allow_already_armed`` is not set.
    ``build_sha`` and ``expected_services`` are required: the alerts and G22 records must carry the sha, and a baseline
    that names no service judges none. Not live (the default): the controller's dry run, no estate call at all."""
    armed = False
    if live:
        armed = estate.override_present()
        if armed and not allow_already_armed:
            try:
                records.append("refused", stage=STAGE, reason=REFUSE_ARMED)
            except OSError:
                pass                                 # the refusal stands even when it cannot be recorded
            raise sc.Refused(REFUSE_ARMED)
    controller = sc.Controller(records, Stage2Actions(estate, armed_before=armed), estate=alert_estate, env=env,
                               expected_services=expected_services, build_sha=build_sha)
    return controller.run(STAGE, go_sentence=go_sentence, live=live)
