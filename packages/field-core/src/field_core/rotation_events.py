"""The ``keyrotation.*`` ledger event schema, FROZEN in slice R2 (key rotation
design v0.2 section 5.1, O15) so the rotator (R4a, R9, R7) and the evidence
tools (R6: ``rotation_audit.py``, ``phase_g_check --rotation``) can be built in
parallel against one contract.

Written by the rotator under ``svc-rotator-<estate>`` (``ledger_attribute``,
``event_prefixes: ["keyrotation."]``); the monitor writes ``keyrotation.overdue``.
Payloads hold only ids, 16-hex key fingerprints (the first 16 hex of the key's
sha256; 8 hex is grindable, S11), generations, 16-hex file / roster sha
prefixes, phases and reason CLASSES. Never a key, never a full hash, never free
text. :func:`validate` enforces exactly that: every event has exactly its listed
fields (no more, no fewer), every value its type, and no string anywhere in a
payload is a 64-hex hash or carries the key prefix.

Changing a name, a field or an allowed value is a schema change: it needs its
own reviewed PR that updates this module, its tests and every writer and
reader at once. Adding a value to an enum is such a change too.

Field types (``FIELD_TYPES``):

* ``operator_id``: an operator id (``operator_auth.printable_id``)
* ``operator_ids``: a list of operator ids (at most 64)
* ``estate``: a short lower-case estate name (``gb10``, ``fly``, a customer id)
* ``run_id`` / ``request_id``: a short id (``[A-Za-z0-9._:-]{1,64}``)
* ``old_fp`` / ``new_fp`` / ``fp``: 16 lower-case hex
* ``generation``: an integer >= 1
* ``registry_sha16``: 16 lower-case hex (the operators file sha256 prefix)
* ``not_before`` / ``until``: ``YYYY-MM-DDTHH:MM:SSZ``
* ``reverted``: a boolean
* ``count`` / ``previous_count``: an integer >= 0
* ``service``: one of the eight operator-block service names
* everything else: one value of its enum below
"""

from __future__ import annotations

import re
from typing import Any

from field_core import operator_auth as oa

PREFIX = "keyrotation."

#: design 4.3 phases (step 0 PREFLIGHT ... 11 CLEANUP)
PHASES = frozenset({
    "preflight", "lock", "precheck", "generate", "publish", "verify_next", "switch",
    "confirm_switch", "soak", "promote", "verify_current", "confirm_refused", "cleanup",
})
#: why a run started (5.1)
START_REASONS = frozenset({"schedule", "incident", "request", "recovery"})
#: why a run was skipped (5.1)
SKIP_REASONS = frozenset({"freeze", "lock", "precheck", "foreign_edit", "clock"})
#: why a run failed or was aborted (5.1 "incl. policy"; 4.3, 4.4)
REASON_CLASSES = frozenset({
    "policy",            # diff_guard refused the candidate
    "validation",        # the candidate failed the installed parser
    "publish_not_seen",  # not every service showed the new file within one tick
    "registry_error",    # a service reported last_registry_error
    "verify_mismatch",   # a verify-hash answer was not the expected slot / window
    "switch_not_seen",   # the daemon's identity_key_fp did not move to new_fp
    "refusal_seen",      # operator.unauthenticated / operator.refused named the id in the soak
    "timeout",           # the 24 h limit before PROMOTE (O4)
    "foreign_edit",      # someone else changed the file
    "clock",             # PREFLIGHT clock checks
    "io",                # a file operation failed
    "operator",          # a human ran --abort-inflight
    "internal",          # anything else (a bug)
})
#: why a key expiry was extended (4.4 O20); free text is never ledgered
EXTEND_REASONS = frozenset({"human_migration", "incident", "recovery", "operator"})
#: spool request types (3.3)
REQUEST_TYPES = frozenset({"passkey_enrol", "passkey_remove", "breakglass_reseal",
                           "breakglass_revoke"})
OVERDUE_SEVERITIES = frozenset({"warn", "critical"})
#: 5.3: oldest current key > 35 d / no completed rotation in 35 d / within 14 d of key_not_after
OVERDUE_REASONS = frozenset({"key_age", "no_completion", "expiry_near", "expired"})
SERVICES = frozenset({"sealed-ledger", "agent-registry", "delegation-authority", "kill-switch",
                      "spend-governor", "federation-broker", "ops-console", "lifecycle-manager"})
#: actions an expired kill-switch key may be used for under K4 (kills only)
EXPIRED_KEY_ACTIONS = frozenset({"kill", "killed_patch"})

_ID = ("operator_id",)
_RUN = ("estate", "run_id")

#: event type -> its exact field set (design 5.1)
EVENTS: dict[str, frozenset[str]] = {
    "keyrotation.started": frozenset({*_ID, *_RUN, "reason", "old_fp"}),
    "keyrotation.published": frozenset({*_ID, *_RUN, "new_fp", "generation", "registry_sha16"}),
    "keyrotation.cutover": frozenset({*_ID, *_RUN, "new_fp"}),
    "keyrotation.retired": frozenset({*_ID, *_RUN, "old_fp", "generation", "registry_sha16"}),
    "keyrotation.completed": frozenset({*_ID, *_RUN, "old_fp", "new_fp", "generation"}),
    "keyrotation.failed": frozenset({*_ID, *_RUN, "phase", "reason_class", "reverted"}),
    "keyrotation.aborted": frozenset({*_ID, *_RUN, "phase", "reason_class", "reverted"}),
    "keyrotation.skipped": frozenset({*_ID, *_RUN, "skip_reason"}),
    "keyrotation.reconciled": frozenset({*_RUN, "operator_ids", "generation", "registry_sha16"}),
    "keyrotation.extended": frozenset({*_ID, *_RUN, "until", "extend_reason"}),
    "keyrotation.recovery_started": frozenset({*_RUN, "operator_ids"}),
    "keyrotation.recovery_ended": frozenset({*_RUN}),
    "keyrotation.requested": frozenset({*_ID, "estate", "request_id", "request_type",
                                        "not_before"}),
    "keyrotation.enrolled": frozenset({*_ID, "estate", "request_id", "request_type",
                                       "generation"}),
    "keyrotation.cancelled": frozenset({*_ID, "estate", "request_id", "request_type"}),
    "keyrotation.overdue": frozenset({*_ID, "estate", "severity", "overdue_reason"}),
    "keyrotation.breakglass_used": frozenset({"estate", "service", "count", "previous_count"}),
    "keyrotation.breakglass_attempt": frozenset({"estate", "service", "count", "previous_count"}),
    "keyrotation.expired_key_used": frozenset({*_ID, "estate", "service", "fp", "action"}),
    "keyrotation.seed_stale": frozenset({*_ID, "estate"}),
}

#: fields whose value may be null: a skip before an identity was chosen (lock
#: held, freeze) names none
NULLABLE = {"keyrotation.skipped": frozenset({"operator_id"})}

_FP16 = re.compile(r"^[0-9a-f]{16}$")
_ESTATE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
_SHORT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_HEX64_ANYWHERE = re.compile(r"[0-9a-fA-F]{64}")
MAX_OPERATOR_IDS = 64


def _enum(values: frozenset[str]):
    return lambda v: isinstance(v, str) and v in values


def _gen(v: Any) -> bool:
    return type(v) is int and v >= 1


def _count(v: Any) -> bool:
    return type(v) is int and v >= 0


def _ids(v: Any) -> bool:
    return (isinstance(v, list) and len(v) <= MAX_OPERATOR_IDS
            and all(oa.printable_id(x) for x in v) and len(set(v)) == len(v))


FIELD_TYPES: dict[str, Any] = {
    "operator_id": oa.printable_id,
    "operator_ids": _ids,
    "estate": lambda v: isinstance(v, str) and _ESTATE.fullmatch(v) is not None,
    "run_id": lambda v: isinstance(v, str) and _SHORT_ID.fullmatch(v) is not None,
    "request_id": lambda v: isinstance(v, str) and _SHORT_ID.fullmatch(v) is not None,
    "old_fp": lambda v: isinstance(v, str) and _FP16.fullmatch(v) is not None,
    "new_fp": lambda v: isinstance(v, str) and _FP16.fullmatch(v) is not None,
    "fp": lambda v: isinstance(v, str) and _FP16.fullmatch(v) is not None,
    "registry_sha16": lambda v: isinstance(v, str) and _FP16.fullmatch(v) is not None,
    "generation": _gen,
    "not_before": lambda v: oa.parse_time(v) is not None,
    "until": lambda v: oa.parse_time(v) is not None,
    "reverted": lambda v: type(v) is bool,
    "count": _count,
    "previous_count": _count,
    "reason": _enum(START_REASONS),
    "skip_reason": _enum(SKIP_REASONS),
    "phase": _enum(PHASES),
    "reason_class": _enum(REASON_CLASSES),
    "extend_reason": _enum(EXTEND_REASONS),
    "request_type": _enum(REQUEST_TYPES),
    "severity": _enum(OVERDUE_SEVERITIES),
    "overdue_reason": _enum(OVERDUE_REASONS),
    "service": _enum(SERVICES),
    "action": _enum(EXPIRED_KEY_ACTIONS),
}


class SchemaError(ValueError):
    """A keyrotation.* event that does not match the frozen schema. The message
    names the event type and field NAMES only, never a value."""


def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def validate(event_type: str, payload: Any) -> None:
    """Raise SchemaError unless ``payload`` is exactly a frozen ``event_type``
    event. Checked: the type is listed; the field set is exact; each value has
    its field's type; and (defence in depth: no field type admits one today)
    no string anywhere is or contains a 64-hex run or the key prefix."""
    if event_type not in EVENTS:
        raise SchemaError("unknown keyrotation event type")
    if not isinstance(payload, dict):
        raise SchemaError(f"{event_type}: payload must be an object")
    want = EVENTS[event_type]
    have = set(payload)
    if have != want:
        missing, extra = sorted(want - have), sorted(have - want)
        raise SchemaError(f"{event_type}: fields differ (missing {missing}, unexpected "
                          f"{len(extra)} field(s))")
    nullable = NULLABLE.get(event_type, frozenset())
    for name in sorted(want):
        value = payload[name]
        if value is None and name in nullable:
            continue
        if not FIELD_TYPES[name](value):
            raise SchemaError(f"{event_type}: field {name!r} has a value of the wrong type or form")
    for s in _strings(payload):
        if oa.KEY_PREFIX in s or _HEX64_ANYWHERE.search(s):
            raise SchemaError(f"{event_type}: a value looks like a key or a full hash")


def fingerprint(key_sha256_hex: str) -> str:
    """The 16-hex fingerprint these events carry, from a key's sha256 hex."""
    if not isinstance(key_sha256_hex, str) or not re.fullmatch(r"[0-9a-f]{64}", key_sha256_hex):
        raise SchemaError("fingerprint needs a 64 lower-case hex sha256")
    return key_sha256_hex[:16]
