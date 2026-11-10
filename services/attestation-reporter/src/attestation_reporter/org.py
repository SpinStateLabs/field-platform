"""The org name a board pack is issued for (S4-17).

``org`` lands inside the signed ``board-pack.json`` and the HTML, so it is a name you can SEE on one line: non-blank,
at most ``MAX_ORG_CHARS``, and free of control (Cc), invisible format / bidirectional (Cf) and line or paragraph
separator (Zl, Zp) characters. The same rule ``compliance_crosswalk.evidence_pack`` applies to a signer (C-389).
Refusals are fixed text (a code point and position at most), never the caller's value.
"""

from __future__ import annotations

import unicodedata

MAX_ORG_CHARS = 200
# Cs: a lone surrogate (from a POSIX argv holding invalid UTF-8) cannot be encoded as UTF-8 and used to crash the CLI in
# the JSON serialiser (R-PR665 C2). Private-use (Co) and unassigned (Cn) code points serialise fine and stay accepted: a
# decision recorded here, they only weaken the "a name you can SEE" aim.
_REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})


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
                f"the org holds a control, invisible, line-break or unencodable character (U+{ord(ch):04X} at position "
                f"{position}); an org is a name on one line"
            )
    return text


MAX_SIGNER_CHARS = 200


class InvalidSigner(ValueError):
    """A signer that is not a visible one-line name (CLI exit 2; served signing stays UNSIGNED)."""


def checked_signer(signer: object) -> str:
    """The stripped signer, or ``InvalidSigner``. The same rule as ``checked_org`` (S9-17): the name lands inside the
    signed ``board-pack.json`` and is echoed to a terminal, so it must be a name you can SEE on one line. Refusals are
    fixed text (a count, or a code point and position), never the caller's value."""
    if not isinstance(signer, str) or not signer.strip():
        raise InvalidSigner("signer must name the human signing the pack (blank refused)")
    text = signer.strip()
    if len(text) > MAX_SIGNER_CHARS:
        raise InvalidSigner(f"the signer is {len(text)} characters; the limit is {MAX_SIGNER_CHARS}")
    for position, ch in enumerate(text):
        if unicodedata.category(ch) in _REFUSED_CATEGORIES:
            raise InvalidSigner(
                f"the signer holds a control, invisible, line-break or unencodable character (U+{ord(ch):04X} at "
                f"position {position}); a signer is a name on one line"
            )
    return text
