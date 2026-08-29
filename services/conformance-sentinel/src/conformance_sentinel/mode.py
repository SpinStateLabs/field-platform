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


def resolve_mode(default: SentinelMode = SentinelMode.LOG_ONLY) -> SentinelMode:
    """Read the estate-wide mode from ``FIELD_SENTINEL_MODE`` (default log_only)."""
    raw = os.environ.get("FIELD_SENTINEL_MODE", "").strip().lower().replace("-", "_")
    if raw in ("log_only", "logonly"):
        return SentinelMode.LOG_ONLY
    if raw in ("enforce", "enforcing", "enforced"):
        return SentinelMode.ENFORCE
    return default
