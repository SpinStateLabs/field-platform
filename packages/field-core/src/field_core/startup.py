"""One loud line when a service starts OPEN (C-804, Don ruling D-21).

The committed demo defaults leave the perimeter secret empty, the operator
layer off, ledger signing not required and the gateway in observer mode. Those
defaults stay (no refusal, the demo compose is unchanged); this module only
makes the state visible: each service calls :func:`warn_open` once at start
and, when any of the settings is open, one WARNING per process names the
SETTINGS (variable names, never a value) that are open.

Operator ``log-only`` (a registry configured, ``FIELD_OPERATOR_REQUIRE`` not
set) does NOT count as open here: that layer is ON, it observes and records but
does not refuse. Only mode ``off`` is named; ``enforce`` is silent. (A reader
who wants log-only called out too would widen ``open_settings`` and its tests.)

Only names are ever formatted into the line. A value that is passed by mistake
(anything outside the ``UPPER_SNAKE`` variable-name shape) is dropped, so a
caller bug cannot turn the line into a leak.
"""

from __future__ import annotations

import logging
import re
import threading

log = logging.getLogger("field_core.startup")

_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")  # 1 to 64 characters, used with fullmatch
_warned: set[str] = set()
_lock = threading.Lock()


def open_settings(*, operator_layer: bool = False, extra=()) -> list[str]:
    """Names of the settings that leave this process open: the perimeter secret
    (``FIELD_SHARED_SECRET`` empty), the operator layer (only for a service that
    has one, mode OFF; log-only is not off) and the service's own ``extra`` names (callers pass a
    name only when that setting is off). Never a value."""
    from field_core import authn, operator_auth

    names: list[str] = []
    if authn.shared_secret() is None:
        names.append(authn.ENV_VAR)
    if operator_layer and operator_auth.mode() == operator_auth.OFF:
        names.append(operator_auth.ENV_REQUIRE)
    names.extend(x for x in extra if isinstance(x, str) and _NAME.fullmatch(x))
    return names


def warn_open(service: str, *, operator_layer: bool = False, extra=()) -> bool:
    """Log the open-mode line for ``service`` once per process. Returns True
    when it logged. Never raises: a startup warning must not stop a service."""
    try:
        names = open_settings(operator_layer=operator_layer, extra=extra)
        if not names:
            return False
        with _lock:
            if service in _warned:
                return False
            _warned.add(service)
        log.warning(
            "%s started OPEN (demo mode): %s not enforced. Fine for a local demo; "
            "set them for any shared or deployed use.",
            service, ", ".join(names))
        return True
    except Exception:  # pragma: no cover - the line is advisory
        return False


def _reset_for_tests() -> None:
    with _lock:
        _warned.clear()
