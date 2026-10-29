"""One reading of a 0/1 posture switch, shared by the services that read the same variable (C-180).

A posture flag decides whether a control is armed. Exact-match ``== "1"`` made ``true``, ``yes``, ``on``, ``2``
and `` 1`` all mean "off" without a word, so a spelling the operator believed meant on left the control off.
Recognised spellings (case-insensitive, surrounding whitespace ignored): true ``1 true yes on``, false
``0 false no off``. Unset or blank is the caller's default (off). Anything else is *unrecognised*: ``parse``
returns None and the caller decides, which for a posture is to refuse to start (or, where it cannot, to treat the
flag as armed), never to read it as off."""

from __future__ import annotations

TRUE_SPELLINGS = ("1", "true", "yes", "on")
FALSE_SPELLINGS = ("0", "false", "no", "off")


def parse(raw: str | None) -> bool | None:
    """True or False for a recognised spelling, False for unset or blank, None for anything else."""
    text = (raw or "").strip().lower()
    if text == "":
        return False
    if text in TRUE_SPELLINGS:
        return True
    if text in FALSE_SPELLINGS:
        return False
    return None
