"""Sentinel operating mode — safe-by-default log-only (ADR 02 + brief safety rule).

- ``log_only``: verdicts are computed and **shadow-ledgered** as would-block /
  would-escalate, but the caller is never blocked — every ``/check`` returns
  ALLOW. A new estate observes before it enforces; one env var reverts the whole
  estate here.
- ``enforce``: verdicts block / escalate for real (the fully-capable behavior).

Two defaults, deliberately:
- ``resolve_mode()`` (env ``FIELD_SENTINEL_MODE``) defaults to **log_only**, so a
  *served* estate is safe-by-default.
- ``SentinelEngine``'s constructor defaults to **enforce**, so programmatic and
  test use gets the fully-capable path unless told otherwise (keeps existing
  unit tests, which assert real blocks, unchanged).

Demos and CI that showcase enforcement set ``FIELD_SENTINEL_MODE=enforce``.
"""

from __future__ import annotations

import os
from enum import Enum


class SentinelMode(str, Enum):
    LOG_ONLY = "log_only"
    ENFORCE = "enforce"


class InvalidSentinelMode(ValueError):
    """``FIELD_SENTINEL_MODE`` is set to something that is neither a log-only nor an enforce spelling."""


def resolve_mode(default: SentinelMode = SentinelMode.LOG_ONLY) -> SentinelMode:
    """Read the estate-wide mode from ``FIELD_SENTINEL_MODE`` (unset or blank: ``default``, log_only).

    A non-empty value that is not a recognised spelling raises ``InvalidSentinelMode`` (C-169, D-23): log-only
    allows every ``/check``, so a typo (``enfroce``, ``on``, ``true``) must not quietly mean "observe only"."""
    raw = os.environ.get("FIELD_SENTINEL_MODE", "").strip().lower().replace("-", "_")
    if raw == "":
        return default
    if raw in ("log_only", "logonly"):
        return SentinelMode.LOG_ONLY
    if raw in ("enforce", "enforcing", "enforced"):
        return SentinelMode.ENFORCE
    # The value is NOT echoed (C-377): a variable pointed at a secret by mistake must not land in a log.
    raise InvalidSentinelMode(
        f"FIELD_SENTINEL_MODE is set to an unrecognised value ({len(raw)} characters); use log_only or enforce "
        "(or leave it unset for log_only)")
