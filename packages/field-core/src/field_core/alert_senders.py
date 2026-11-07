"""The senders for the six production alert classes (G23; Don's ruling lifted C-552).

``field_core.alerts`` is the library: one ``send`` for a class, with the content check, the retries and the
counters. This module is what a service or a tool calls. One function per class, and one mapping from a ledger event
to the class it should raise, so a caller does not choose a class by hand and the same event always raises the same
alert.

**A sender never raises.** A bad argument, a missing topic, an unreachable server: the result says so, the failure is
counted (``alerts_failed``, surfaced by ``alerts.health_fields()`` in the caller's ``GET /health``) and logged. An
alert that fails must not stop the work that raised it. An argument outside the alert charset is withheld by the
content check, like any other field; the alert is still sent.

**What has a caller on main.** ``breakglass_used`` is sent by the sealed-ledger operator observer, on every
``operator.breakglass_counters_changed`` row it writes (one alert per row). The other five have no caller on main
yet: ``rotation_failed``, ``rotation_overdue`` and ``rotation_halted`` wait for the rotator (PR 57 rework, C-496), and
``stage_transition`` and ``stage_aborted`` wait for the Phase G stage controller, which is not in this repository.
They are built and tested here so a caller only has to call them. ``keyrotation.*`` has no ``halted`` event
(``rotation_events.EVENTS``), so ``rotation_halted`` has a sender and no ledger-event mapping: adding the event is a
schema change that needs its own reviewed PR.

No alert carries a key, a token, a hash or a topic: the fields are ids and fixed words, and ``alerts.render`` checks
every field and the rendered text again.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from field_core import alerts

log = logging.getLogger("field_core.alert_senders")

#: Names the estate in an alert (``gb10``, ``fly``). Unset: ``unknown``. The host name is not used as a default,
#: because a container or machine id is hex and the content check withholds it (runbook, section 1 step 4).
ENV_ESTATE = "FIELD_ESTATE"
DEFAULT_ESTATE = "unknown"


def estate_name(env: Mapping[str, str] | None = None) -> str:
    """The estate named in an alert: ``FIELD_ESTATE`` when set and not blank, else ``unknown``."""
    value = (env if env is not None else os.environ).get(ENV_ESTATE)
    value = value.strip() if isinstance(value, str) else ""
    return value or DEFAULT_ESTATE


def _fixed(alert_class: str, *, estate: str | None, subject: Any, detail: Any,
           env: Mapping[str, str] | None, **kwargs) -> alerts.AlertResult:
    """Send one alert. Never raises: a failure is counted and logged here when the library did not get that far."""
    try:
        return alerts.send(alert_class, estate=estate or estate_name(env),
                           subject=None if subject is None else str(subject),
                           detail=None if detail is None else str(detail), env=env, **kwargs)
    except Exception as exc:  # never let an alert stop the work that raised it
        reason = f"sender_error_{type(exc).__name__}"[:60]
        alerts._count_failure(alert_class, reason, 0)
        return alerts.AlertResult(False, alert_class, 0, reason)


def rotation_failed(*, subject: Any = None, detail: Any = None, estate: str | None = None,
                    env: Mapping[str, str] | None = None, **kwargs) -> alerts.AlertResult:
    """A key rotation failed (the rotator, ``keyrotation.failed``)."""
    return _fixed("rotation_failed", estate=estate, subject=subject, detail=detail, env=env, **kwargs)


def rotation_overdue(*, subject: Any = None, detail: Any = None, estate: str | None = None,
                     env: Mapping[str, str] | None = None, **kwargs) -> alerts.AlertResult:
    """No rotation completed in time, or a key is near its expiry (``keyrotation.overdue``)."""
    return _fixed("rotation_overdue", estate=estate, subject=subject, detail=detail, env=env, **kwargs)


def rotation_halted(*, subject: Any = None, detail: Any = None, estate: str | None = None,
                    env: Mapping[str, str] | None = None, **kwargs) -> alerts.AlertResult:
    """The rotator stopped after repeated faults and will not retry by itself."""
    return _fixed("rotation_halted", estate=estate, subject=subject, detail=detail, env=env, **kwargs)


def breakglass_used(*, subject: Any = None, detail: Any = None, estate: str | None = None,
                    env: Mapping[str, str] | None = None, **kwargs) -> alerts.AlertResult:
    """The break-glass identity authenticated or was tried."""
    return _fixed("breakglass_used", estate=estate, subject=subject, detail=detail, env=env, **kwargs)


def stage_transition(*, subject: Any = None, detail: Any = None, estate: str | None = None,
                     env: Mapping[str, str] | None = None, **kwargs) -> alerts.AlertResult:
    """The Phase G stage controller moved one step (one alert per step, P36)."""
    return _fixed("stage_transition", estate=estate, subject=subject, detail=detail, env=env, **kwargs)


def stage_aborted(*, subject: Any = None, detail: Any = None, estate: str | None = None,
                  env: Mapping[str, str] | None = None, **kwargs) -> alerts.AlertResult:
    """The Phase G stage controller aborted a stage and rolled back."""
    return _fixed("stage_aborted", estate=estate, subject=subject, detail=detail, env=env, **kwargs)


#: alert class -> its sender. Exactly the six production classes of ``alerts.CLASSES`` (``test`` has its own
#: ``alerts.send_test``); a test keeps the two in step.
SENDERS = {
    "rotation_failed": rotation_failed,
    "rotation_overdue": rotation_overdue,
    "rotation_halted": rotation_halted,
    "breakglass_used": breakglass_used,
    "stage_transition": stage_transition,
    "stage_aborted": stage_aborted,
}

#: ledger event type -> the alert class it raises. ``keyrotation.aborted`` is not here on purpose: it is an operator
#: abort of one rotation, not the ``stage_aborted`` of a Phase G stage. ``keyrotation.breakglass_attempt`` is a use
#: for this purpose: the class text says "authenticated or was tried".
EVENT_CLASS = {
    "keyrotation.failed": "rotation_failed",
    "keyrotation.overdue": "rotation_overdue",
    "keyrotation.breakglass_used": "breakglass_used",
    "keyrotation.breakglass_attempt": "breakglass_used",
    "operator.breakglass_counters_changed": "breakglass_used",
}


def _word(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _subject_and_detail(event_type: str, payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Ids and fixed words only, never a free-text field: the payload schemas hold none, and the content check
    still runs on what is built here."""
    if event_type == "keyrotation.failed":
        detail = f"phase {_word(payload.get('phase'))}, reason {_word(payload.get('reason_class'))}"
        if payload.get("reverted") is True:
            detail += ", reverted"
        return _word(payload.get("operator_id")) or None, detail
    if event_type == "keyrotation.overdue":
        detail = f"{_word(payload.get('severity'))}, {_word(payload.get('overdue_reason'))}"
        return _word(payload.get("operator_id")) or None, detail
    if event_type == "operator.breakglass_counters_changed":
        return (_word(payload.get("service")) or None,
                f"auth {payload.get('breakglass_auth_count')}, attempt {payload.get('breakglass_attempt_count')}")
    # keyrotation.breakglass_used / keyrotation.breakglass_attempt
    return _word(payload.get("service")) or None, f"count {payload.get('count')}"


def alert_for_event(event_type: str, payload: Mapping[str, Any] | None = None, *,
                    estate: str | None = None, env: Mapping[str, str] | None = None,
                    **kwargs) -> alerts.AlertResult | None:
    """Send the alert a ledger event calls for. ``None`` when the event type raises none; otherwise exactly one
    alert for this call, and the result. Never raises."""
    alert_class = EVENT_CLASS.get(event_type)
    if alert_class is None:
        return None
    try:
        subject, detail = _subject_and_detail(event_type, payload if isinstance(payload, Mapping) else {})
    except Exception:  # a payload of an unexpected shape still raises its alert, without the details
        subject, detail = None, None
    return SENDERS[alert_class](subject=subject, detail=detail, estate=estate, env=env, **kwargs)
