"""Caller text shown on ONE line of generated Markdown (C-1082 F-CW-3, reviewer Q-47).

A value the caller supplies (an ``agent_id``, a ledger reason, a stale-flag reason) must not be able to start a new
Markdown block: a newline would open a heading or a ``Signer:`` line, a ``|`` would add a table column. The
characters a signer may not hold (control, invisible format, line and paragraph separators, and unpaired
surrogates) are shown as ``<U+XXXX>`` instead of written; text beyond ``MAX_LINE_CHARS`` of the ESCAPED line is cut
with an ellipsis, never in the middle of a ``<U+XXXX>`` token. Ordinary text, including non-ASCII letters, is
unchanged."""

from __future__ import annotations

import unicodedata
from typing import Any

#: Longest caller-supplied text shown on one line, counted after escaping.
MAX_LINE_CHARS = 300
#: Unicode categories shown as a code point, and refused in a signer: control (Cc), invisible format (Cf: marks,
#: zero-width characters, byte-order mark, bidirectional overrides and isolates), line and paragraph separator (Zl,
#: Zp), and unpaired surrogate (Cs: it cannot be encoded as UTF-8, so a response carrying it is a server error).
REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})


def one_line(value: Any, limit: int = MAX_LINE_CHARS, *, escape_pipe: bool = False) -> str:
    """``value`` as text on one line (see the module docstring). ``escape_pipe`` also writes ``|`` as ``\\|``, for a
    Markdown table cell."""
    out: list[str] = []
    used = 0
    for ch in str(value):
        if unicodedata.category(ch) in REFUSED_CATEGORIES:
            piece = f"<U+{ord(ch):04X}>"
        elif escape_pipe and ch == "|":
            piece = "\\|"
        else:
            piece = ch
        if used + len(piece) > limit:
            return "".join(out) + "…"
        out.append(piece)
        used += len(piece)
    return "".join(out)
