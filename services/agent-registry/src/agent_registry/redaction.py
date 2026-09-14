"""Credential-shaped string patterns and their redaction (v1.2 D3).

Pure functions, no package imports, so ``models`` can redact at the model
layer without a cycle through ``discover``.

``KEY_PATTERNS`` is ORDERED. A scan takes each pattern in turn and a later
pattern never claims characters an earlier one already matched, so an
Anthropic ``sk-ant-…`` key is counted once as ``anthropic`` and never again
as the BROAD ``sk-`` pattern that follows it.

Every pattern carries a ``breadth`` label, because a heuristic that does not
say how often it is wrong overclaims:

* ``low``        — a provider-specific prefix and length; false positives rare
* ``moderate``   — a short prefix that ordinary identifiers can share
* ``broad``      — ``sk-`` / ``sk-proj-``: many non-OpenAI strings start so
* ``generic``    — shape only (JWT); a hit says "token-shaped", not "whose"
* ``very-broad`` — ``api_key|secret|token = value`` assignments; OFF by
  default (``include_very_broad=True`` turns it on)

Boundaries: in a SCAN every pattern refuses to start in the middle of a
longer identifier (``task-…`` never matches ``sk-``) and the fixed-length
patterns refuse to end in one (a 40-character ``AIza…`` string is not a
39-character Google key). REDACTION of echoed strings is looser (see
:func:`redact_text`).

Redaction (:func:`redact`): the first 7 characters, an ellipsis, the last 4,
never more than half of the value; plus a sha256 fingerprint (first 16 hex)
so the same secret can be correlated across reports without being carried.
The fingerprint of a LOW-ENTROPY value (a very-broad ``token=password1``
hit) is guessable by brute force — README LIMITS says so.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

#: Largest text any scanner input may carry, in UTF-8 bytes (1 MiB).
MAX_SCAN_BYTES = 1024 * 1024


class ScanInputError(ValueError):
    """A scanner input that is oversized or malformed. Its message names the
    input and the line, never a value from it, so the API can return it as
    the 422 detail. Deliberately NOT pydantic's ValidationError (also a
    ValueError), whose text carries ``input_value=`` — a raw secret."""


# A match may not begin right after (or, for fixed lengths, end right before)
# one of these: they would make it part of a longer identifier.
_WORD = r"A-Za-z0-9_\-"
_START = rf"(?<![{_WORD}])"
_END = rf"(?![{_WORD}])"
# Redaction's looser start, for the BROAD ``sk-`` pattern only: only a letter
# or digit blocks it, so a key glued on with ``-`` or ``_`` (``wf-<key>``) is
# still redacted, while ``task-…``, ``desk-booking-…`` and ``risk-scoring-…``
# stay readable. Every provider-prefixed pattern has NO start boundary at all
# when redacting (D3-R5): ``prod<sk-ant-key>`` is redacted, and a false match
# inside an ordinary identifier is rare and, in an echo, the safe error.
_LOOSE_START = r"(?<![A-Za-z0-9])"


@dataclass(frozen=True)
class KeyPattern:
    name: str
    breadth: str
    #: Bounded: refuses to start (and, where ``end`` is set, to end) inside a
    #: longer identifier. What ``scan_secrets_text`` reports.
    regex: re.Pattern[str]
    #: The same body with no end boundary and no start boundary — or, for a
    #: pattern built ``glued=False``, only ``_LOOSE_START``. What
    #: :func:`redact_text` uses on echoed strings, where over-redacting is the
    #: safe error.
    loose: re.Pattern[str]
    #: Regex group holding the secret value (0 = the whole match).
    group: int = 0


def _pattern(name: str, breadth: str, body: str, end: bool = False,
             glued: bool = True) -> KeyPattern:
    """``glued=False`` keeps ``_LOOSE_START`` on the redaction regex: for a
    prefix that ordinary words end in (``task-``, ``desk-``), where redacting a
    key glued onto a letter or digit would mangle readable identifiers."""
    return KeyPattern(name, breadth,
                      re.compile(_START + body + (_END if end else "")),
                      re.compile(("" if glued else _LOOSE_START) + body))


KEY_PATTERNS: tuple[KeyPattern, ...] = (
    _pattern("anthropic", "low", r"sk-ant-[A-Za-z0-9_\-]{32,}"),
    _pattern("openai-style-sk", "broad", r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}",
             glued=False),
    _pattern("google-api-key", "low", r"AIza[0-9A-Za-z_\-]{35}", end=True),
    _pattern("huggingface", "moderate", r"hf_[A-Za-z0-9]{30,}", end=True),
    _pattern("aws-access-key-id", "low", r"(?:AKIA|ASIA)[0-9A-Z]{16}", end=True),
    _pattern("github-token", "low", r"gh[pousr]_[A-Za-z0-9]{36,}", end=True),
    _pattern("slack-token", "low", r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    _pattern("stripe-secret-key", "low", r"sk_(?:live|test)_[A-Za-z0-9]{16,}", end=True),
    _pattern("google-oauth-access-token", "low", r"ya29\.[A-Za-z0-9_\-]{20,}"),
    _pattern("jwt", "generic",
             r"eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
)

#: Ships OFF: ``(api_key|secret|token)=value`` flags every config file and
#: every test fixture in existence. Opt in per scan.
_ASSIGNMENT = re.compile(r"(?i)(?<![A-Za-z0-9_])(?:api_key|secret|token)\s*=\s*[\"']?"
                         r"([^\s\"',;]{12,})")
VERY_BROAD_PATTERN = KeyPattern("assignment", "very-broad", _ASSIGNMENT, _ASSIGNMENT, group=1)


def fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def redact(value: str) -> str:
    """``prefix7…last4`` — but never more than half the value is shown."""
    if len(value) >= 22:
        return f"{value[:7]}…{value[-4:]}"
    return f"{value[: len(value) // 4]}…"


@dataclass(frozen=True)
class RawHit:
    """One match, still holding the raw value. Never serialised: the report
    model (``models.SecretHit``) takes the value and keeps only its redaction."""

    pattern: str
    breadth: str
    value: str
    start: int
    end: int


def check_size(text: str, label: str) -> None:
    size = len(text.encode("utf-8"))
    if size > MAX_SCAN_BYTES:
        raise ScanInputError(
            f"{label} is {size} bytes; the scanner accepts at most "
            f"{MAX_SCAN_BYTES} (1 MiB)"
        )


def find_secrets(text: str, *, include_very_broad: bool,
                 bounded: bool = True) -> list[RawHit]:
    """Every credential-shaped string, in text order, each span counted once
    (the first pattern in ``KEY_PATTERNS`` order that claims it wins).
    ``bounded=False`` uses the looser redaction boundaries."""
    patterns = KEY_PATTERNS + ((VERY_BROAD_PATTERN,) if include_very_broad else ())
    taken: list[tuple[int, int]] = []
    hits: list[RawHit] = []
    for pattern in patterns:
        regex = pattern.regex if bounded else pattern.loose
        for m in regex.finditer(text):
            start, end = m.span(pattern.group)
            if any(start < t_end and t_start < end for t_start, t_end in taken):
                continue
            taken.append((start, end))
            hits.append(RawHit(pattern.name, pattern.breadth, m.group(pattern.group),
                               start, end))
    hits.sort(key=lambda h: h.start)
    return hits


def redact_text(text: str) -> str:
    """``text`` with every KEY_PATTERNS match replaced by its redaction.
    Used on every string a report echoes back from its input. Loosely
    bounded — a provider-prefixed key glued onto anything (``prod<key>``) and
    a broad ``sk-`` key glued on with ``-``/``_`` (``wf-<key>``) are still
    redacted; a broad ``sk-`` key glued onto a letter or digit is NOT (README
    LIMITS) — and WITH the very-broad assignment pattern: when the output is an echo,
    over-redacting is the safe error, so the noise that keeps that pattern out
    of scans does not apply."""
    hits = find_secrets(text, include_very_broad=True, bounded=False)
    if not hits:
        return text
    out, cursor = [], 0
    for hit in hits:
        out.append(text[cursor:hit.start])
        out.append(f"[REDACTED {hit.pattern} {redact(hit.value)} {fingerprint(hit.value)}]")
        cursor = hit.end
    out.append(text[cursor:])
    return "".join(out)
