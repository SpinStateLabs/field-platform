#!/usr/bin/env python3
"""stage_controller - the Phase G stage controller (P36; G24; Don's ruling lifts C-552).

    python tools/stage_controller.py plan   --stage N [--records PATH] [--go-sentence TEXT]
    python tools/stage_controller.py record alerts-proven | gate G21 | gate G22 [--records PATH]

WHAT IT IS. A state machine for the three Phase G arming stages (``docs/runbooks/v1.2-deploy-rollback.md``,
"Stage pre-flight checklists"). It decides, in order: may this stage start (``preconditions``), what are the steps
(``STAGES``), did a step break anything (``ABORT_CONDITIONS``), and how does the stage roll back. It does NOT touch an
estate: every action goes through an ``Actions`` object the caller supplies (the coordinator's driver), and this file
ships none. The command line has no ``run``: it can print a plan and write the two kinds of record, nothing more.
The first live run is a coordinator and Don step.

DEFAULTS. ``Controller.run`` is a dry run unless ``live=True`` AND an ``Actions`` object was given. A dry run calls no
action, sends no alert and writes a ``plan`` record.

WHAT IT REFUSES (``Refused``; nothing runs, one ``refused`` record). A stage that is unknown. No ``alerts_proven``
record (the test alert reached Don, P36). Stage 2 without the ``G22`` gate record, Stage 3 without ``G21``. Stage 2
and Stage 3 without Don's go sentence passed in as an input (``go_sentence``; never read from the environment, and only
its length and an 8-hex prefix of its sha256 (16 hex would be withheld by the content check) are recorded). Stage 1 is the only stage that runs on the alerts record
alone: "automatic" means Stage 1 steps and the rollbacks until Don says otherwise (G25, G26).

ABORT. Any of the conditions in ``ABORT_CONDITIONS`` after any step rolls the stage back, in the reverse order of the
runbook, and sends exactly one ``stage_aborted`` alert. The controller's own error is one of them (fail closed = roll
back). A rollback that fails, or whose verification fails, sends one ``stage_aborted`` alert saying so and STOPS: it is
never retried and never loops. One ``stage_transition`` alert goes out for each step that completes.

RECORDS. The controller writes only its own rows (``Records``): fixed keys, one JSON object per line, a string value
that fails the alert content check (a key prefix, a hex run, a PEM header) is replaced by ``(withheld)``. It never
prints a key and never reads one. The records file is trusted by file permission only: whoever can write it can
write ``alerts_proven``. Standard library plus ``field_core``.

Exit status of the command line: 0 ok, 2 refused or a usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import enum
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from field_core import alert_senders, alerts

WITHHELD = "(withheld)"
COUNTER_KEYS = ("dropped_unauthenticated_records", "dropped_refused_records")
MAX_GO_SENTENCE = 500


class Abort(str, enum.Enum):
    """The abort conditions (the architect's P36 review). Each one rolls the stage back. Each value is shorter than
    32 characters: a longer run of letters, digits and underscores is an opaque-token run to the alert content check,
    which would withhold the very reason the alert exists to give (a test holds the line)."""
    DROPPED_UNAUTHENTICATED = "dropped_unauth_increase"
    DROPPED_REFUSED = "dropped_refused_increase"
    CHECKLIST_ITEM = "checklist_item_failed"
    PHASE_G_CHECK = "phase_g_check_failed"
    CANARY_C0 = "canary_c0_failed"
    HEALTH = "health_failure"
    RESTART = "restart_failure"
    CONTROLLER_ERROR = "controller_error"


ABORT_CONDITIONS = tuple(a.value for a in Abort)


@dataclass(frozen=True)
class Stage:
    number: int
    #: steps in arming order; each runs through ``Actions.do`` and is then checked
    steps: tuple[str, ...]
    #: rollback steps in the order they run (the runbook's reverse dependency order)
    rollback: tuple[str, ...]
    gates: tuple[str, ...] = ()
    needs_go_sentence: bool = False


#: The stages and their rollback (runbook v1.2-deploy-rollback.md, step 8 and "Stage pre-flight checklists").
STAGES: dict[int, Stage] = {
    1: Stage(1, steps=("install_operators_file", "set_env_paths", "recreate_eight"),
             rollback=("delete_flag_lines", "recreate_eight")),
    2: Stage(2, steps=("write_override", "recreate_killswitch"),
             rollback=("delete_override", "recreate_killswitch"), gates=("G22",), needs_go_sentence=True),
    3: Stage(3, steps=("set_require_flag", "delete_override", "recreate_eight"),
             rollback=("remove_require_flag", "recreate_seven", "recreate_killswitch"),
             gates=("G21",), needs_go_sentence=True),
}


class Actions(Protocol):
    """What the coordinator's driver supplies. None of it is in this repository's controller."""

    def counters(self) -> Mapping[str, Mapping[str, int]]:
        """Per service, ``dropped_unauthenticated_records`` and ``dropped_refused_records`` from its ``/health``."""

    def do(self, stage: int, step: str) -> None:
        """Run an arming step or a rollback step. A raise is a failure of that step."""

    def check(self, stage: int, step: str) -> Sequence[str]:
        """Check after ``step`` (an arming step, or ``rollback_verify`` after a rollback). The ``Abort`` values of
        what failed: the stage checklist item, ``phase_g_check``, canary C0, health, restart. Empty = all passed."""


class Refused(Exception):
    """The stage may not start. ``reason`` is a fixed token."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Records:
    """The controller's own record rows: one JSON object per line, fixed keys, nothing secret."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    @staticmethod
    def _clean(value: Any) -> Any:
        if isinstance(value, str):
            return WITHHELD if alerts.content_problem(value) else value[:200]
        if isinstance(value, (bool, int, float)) or value is None:
            return value
        if isinstance(value, (list, tuple)):
            return [Records._clean(v) for v in value][:50]
        return WITHHELD

    def append(self, kind: str, **fields: Any) -> dict:
        row = {"ts": _now(), "kind": kind, **{k: self._clean(v) for k, v in fields.items()}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        return row

    def rows(self) -> list[dict]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        out = []
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue                     # a damaged line proves nothing
            if isinstance(row, dict):
                out.append(row)
        return out

    def alerts_proven(self) -> bool:
        return any(r.get("kind") == "alerts_proven" and r.get("ok") is True for r in self.rows())

    def gate_ok(self, gate: str) -> bool:
        return any(r.get("kind") == "gate" and r.get("gate") == gate and r.get("ok") is True for r in self.rows())


def _go_fields(go_sentence: Any) -> dict:
    s = go_sentence.strip()
    return {"go_sentence_len": len(s), "go_sentence_sha8": hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]}


def preconditions(stage: int, records: Records, go_sentence: Any = None) -> None:
    """Raise ``Refused`` unless ``stage`` may start. Reads nothing but the records file and its arguments."""
    spec = STAGES.get(stage) if isinstance(stage, int) and not isinstance(stage, bool) else None
    if spec is None:
        raise Refused("unknown_stage")
    if not records.alerts_proven():
        raise Refused("alerts_not_proven")
    for gate in spec.gates:
        if not records.gate_ok(gate):
            raise Refused(f"gate_{gate}_not_recorded")
    if spec.needs_go_sentence:
        if (not isinstance(go_sentence, str) or not go_sentence.strip() or len(go_sentence) > MAX_GO_SENTENCE
                or alerts.content_problem(go_sentence)):
            raise Refused("go_sentence_missing")


def _increases(baseline: Mapping[str, Mapping[str, int]], now: Mapping[str, Mapping[str, int]]) -> set[Abort]:
    """The abort conditions the dropped-record counters show. A service that disappeared, or a counter that is not
    an integer, cannot be judged: that is ``health_failure``."""
    found: set[Abort] = set()
    if not isinstance(now, Mapping):
        return {Abort.HEALTH}
    for service, base in baseline.items():
        cur = now.get(service)
        if not isinstance(cur, Mapping):
            found.add(Abort.HEALTH)
            continue
        for key, abort in zip(COUNTER_KEYS, (Abort.DROPPED_UNAUTHENTICATED, Abort.DROPPED_REFUSED)):
            a, b = base.get(key), cur.get(key)
            if not all(isinstance(v, int) and not isinstance(v, bool) for v in (a, b)):
                found.add(Abort.HEALTH)
            elif b > a:
                found.add(abort)
    return found


@dataclass
class Result:
    status: str                  # dry-run | completed | aborted_rolled_back | rollback_failed
    stage: int
    steps_done: list[str] = field(default_factory=list)
    abort: str | None = None
    rolled_back: list[str] = field(default_factory=list)


class Controller:
    def __init__(self, records: Records, actions: Actions | None = None, *, estate: str | None = None,
                 env: Mapping[str, str] | None = None, expected_services: Sequence[str] | None = None):
        self.records = records
        self.actions = actions
        self.estate = estate
        self.env = env
        #: services the counters baseline must name; an empty baseline is a health failure whatever this is
        self.expected_services = tuple(expected_services or ())

    def _record(self, kind: str, **fields: Any) -> bool:
        """Append a record row. A write that fails is reported, never raised: a records failure must not skip a
        rollback (F-816-1)."""
        try:
            self.records.append(kind, **fields)
        except Exception:
            return False
        return True

    # alerts: the senders never raise, but a driver bug must not skip a rollback either
    def _alert(self, sender, **kw) -> None:
        try:
            sender(estate=self.estate, env=self.env, **kw)
        except Exception:
            pass

    def run(self, stage: int, *, go_sentence: Any = None, live: bool = False) -> Result:
        try:
            preconditions(stage, self.records, go_sentence)
        except Refused as exc:
            self.records.append("refused", stage=stage if isinstance(stage, int) else None, reason=exc.reason)
            raise
        spec = STAGES[stage]
        extra = _go_fields(go_sentence) if spec.needs_go_sentence else {}
        if not live or self.actions is None:
            self.records.append("plan", stage=stage, steps=list(spec.steps), rollback=list(spec.rollback),
                                dry_run=True, **extra)
            return Result("dry-run", stage)
        result = Result("completed", stage)
        interrupt: BaseException | None = None
        try:
            condition = self._arm(spec, result, extra)
        except BaseException as exc:             # KeyboardInterrupt or SystemExit mid-stage: roll back, then re-raise (F-816-2)
            condition, interrupt = Abort.CONTROLLER_ERROR, exc
        if condition is None:
            return result
        aborted = self._abort(spec, condition, result)
        if interrupt is not None:
            raise interrupt
        return aborted

    def _arm(self, spec: Stage, result: Result, extra: Mapping[str, Any]) -> Abort | None:
        """The records, the baseline and the steps, in one guarded region. Returns the abort condition, or None when the
        stage is done and recorded. A records write that fails is a controller error (F-816-1)."""
        stage = spec.number
        if not self._record("stage_start", stage=stage, **extra):
            return Abort.CONTROLLER_ERROR
        try:
            baseline = {s: dict(c) for s, c in self.actions.counters().items()}
        except Exception:
            return Abort.HEALTH
        if not baseline or any(s not in baseline for s in self.expected_services):
            return Abort.HEALTH                  # an empty or short baseline would judge no service (F-816-3)
        for step in spec.steps:
            condition = self._run_step(stage, step, baseline)
            if condition is not None:
                return condition
            result.steps_done.append(step)
            if not self._record("step_done", stage=stage, step=step):
                return Abort.CONTROLLER_ERROR
            self._alert(alert_senders.stage_transition, subject=f"stage{stage}", detail=f"{step} done")
        if not self._record("stage_done", stage=stage):
            return Abort.CONTROLLER_ERROR
        return None

    def _run_step(self, stage: int, step: str, baseline: Mapping[str, Mapping[str, int]]) -> Abort | None:
        try:
            self.actions.do(stage, step)
            failed = {Abort(v) for v in self.actions.check(stage, step)}
            failed |= _increases(baseline, self.actions.counters())
        except Exception:                        # the controller's own error, or a driver's: fail closed
            return Abort.CONTROLLER_ERROR
        if not failed:
            return None
        return sorted(failed, key=lambda a: ABORT_CONDITIONS.index(a.value))[0]

    def _abort(self, spec: Stage, condition: Abort, result: Result) -> Result:
        """Roll back once, in order. A failure stops it: it is never retried."""
        result.abort = condition.value
        self._record("abort", stage=spec.number, condition=condition.value, steps_done=result.steps_done)
        failure: str | None = None
        for step in spec.rollback:
            try:
                self.actions.do(spec.number, step)
            except Exception:
                failure = step
                break
            result.rolled_back.append(step)
            self._record("rollback_step", stage=spec.number, step=step)
        if failure is None:
            try:
                if list(self.actions.check(spec.number, "rollback_verify")):
                    failure = "rollback_verify"
            except Exception:
                failure = "rollback_verify"
        if failure is None:
            result.status = "aborted_rolled_back"
            self._record("rolled_back", stage=spec.number, condition=condition.value)
            self._alert(alert_senders.stage_aborted, subject=f"stage{spec.number}",
                        detail=f"{condition.value}, rolled back")
        else:
            result.status = "rollback_failed"
            self._record("rollback_failed", stage=spec.number, condition=condition.value, step=failure)
            self._alert(alert_senders.stage_aborted, subject=f"stage{spec.number}",
                        detail=f"{condition.value}, ROLLBACK FAILED at {failure}, stopped: act by hand")
        return result


# ------------------------------------------------------------------ command line

def _records_path(arg: str | None) -> Path:
    return Path(arg or "stage-controller-records.jsonl")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="stage_controller", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan", help="print the plan and whether the stage may start (dry run, nothing is changed)")
    plan.add_argument("--stage", type=int, required=True)
    plan.add_argument("--records")
    plan.add_argument("--go-sentence", dest="go_sentence")
    rec = sub.add_parser("record", help="write an alerts-proven or gate record")
    rec.add_argument("what", choices=("alerts-proven", "gate"))
    rec.add_argument("gate", nargs="?", choices=("G21", "G22"))
    rec.add_argument("--records")
    args = ap.parse_args(argv)
    records = Records(_records_path(args.records))
    if args.cmd == "record":
        if args.what == "gate" and not args.gate:
            print("refused: record gate needs G21 or G22")
            return 2
        if args.what == "alerts-proven":
            records.append("alerts_proven", ok=True)
        else:
            records.append("gate", gate=args.gate, ok=True)
        print(f"recorded {args.what}{' ' + args.gate if args.gate else ''}")
        return 0
    try:
        Controller(records).run(args.stage, go_sentence=args.go_sentence)
    except Refused as exc:
        print(f"refused: {exc.reason}")
        return 2
    spec = STAGES[args.stage]
    print(f"stage {args.stage} may start (dry run, nothing was changed)")
    print("steps: " + ", ".join(spec.steps))
    print("rollback, in order: " + ", ".join(spec.rollback))
    print("abort conditions: " + ", ".join(ABORT_CONDITIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
