"""The org name a board pack is issued for (S4-17).

``org`` lands inside the signed ``board-pack.json`` and the HTML, so it is a name you can SEE on one line: non-blank,
at most ``MAX_ORG_CHARS``, and free of control (Cc), invisible format / bidirectional (Cf) and line or paragraph
separator (Zl, Zp) characters. The same rule ``compliance_crosswalk.evidence_pack`` applies to a signer (C-389).
Refusals are fixed text (a code point and position at most), never the caller's value.
"""

from __future__ import annotations

import unicodedata

MAX_ORG_CHARS = 200
_REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


class InvalidOrg(ValueError):
    """An org that is not a visible one-line name (CLI exit 2, API 422)."""


def checked_org(org: object) -> str:
    """The stripped org, or ``InvalidOrg``."""
    if not isinstance(org, str) or not org.strip():
        raise InvalidOrg("the org must be non-blank text")
    text = org.strip()
    if len(text) > MAX_ORG_CHARS:
        raise InvalidOrg(f"the org is {len(text)} characters; the limit is {MAX_ORG_CHARS}")
    for position, ch in enumerate(text):
        if unicodedata.category(ch) in _REFUSED_CATEGORIES:
            raise InvalidOrg(
                f"the org holds a control, invisible or line-break character (U+{ord(ch):04X} at position "
                f"{position}); an org is a name on one line"
            )
    return text
