"""The rules for the text of a stop request (kill, domain kill, revive, drill), in one place.

The kill switch applies them to its request body. A service or command that takes the same text from a person and sends
it on (the console's actions and fleet halt, the lifecycle decommission) applies them at its own edge, before anything
is sent, so that a stop it composes is not refused further along.

* ``reason`` is written to ledger rows and shown to people: one line, not blank, with no control, invisible-format,
  line-separator, paragraph-separator or unpaired surrogate character (Unicode ``Cc``, ``Cf``, ``Zl``, ``Zp``, ``Cs``).
* ``operator`` is held to less: only an unpaired surrogate is refused here, because text holding one cannot be written
  at all. Length and blank rules belong to each model."""

from __future__ import annotations

import unicodedata

_NOT_IN_A_REASON = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})

REASON_RULE = "must be one line, not blank, without control, invisible format or unpaired surrogate characters"
OPERATOR_RULE = "must be valid text (no unpaired surrogate)"


def reason_ok(value: str) -> bool:
    """True for a reason a stop request may carry (length is the caller's own bound)."""
    return bool(value.strip()) and not any(unicodedata.category(ch) in _NOT_IN_A_REASON for ch in value)


def operator_ok(value: str) -> bool:
    """True for operator text that can be written: no unpaired surrogate."""
    return not any(unicodedata.category(ch) == "Cs" for ch in value)


def require_reason(value: str) -> str:
    """For a pydantic ``field_validator``: the value unchanged, or ``ValueError`` (which never repeats it)."""
    if not reason_ok(value):
        raise ValueError(REASON_RULE)
    return value


def require_operator(value: str) -> str:
    """For a pydantic ``field_validator``: the value unchanged, or ``ValueError`` (which never repeats it)."""
    if not operator_ok(value):
        raise ValueError(OPERATOR_RULE)
    return value
