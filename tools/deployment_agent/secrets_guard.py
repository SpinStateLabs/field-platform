"""Secret hygiene helpers: an opaque wrapper and a "looks like a secret" test.

``SecretValue`` never reveals itself through repr/str/format; the only way to
the text is ``.reveal()``, which only the provider adapter and the file stage
call. ``looks_like_secret`` is the guard the journal applies to every string it
is asked to write: it is deliberately over-broad (a false positive costs a
shorter id, a false negative costs a leaked credential).
"""
from __future__ import annotations

import re

_PREFIXES = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:fo1_|FlyV1|fm1r_|fm2_|ghp_|gho_|ghs_|ghu_|github_pat_|sk-|xox[abpr]-|AKIA)",
)
_LONG_RUN = re.compile(r"[A-Za-z0-9+/_=-]{24,}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*-----")
SHA40 = re.compile(r"\A[0-9a-f]{40}\Z")


class SecretValue:
    """Wraps a credential value so a stray log line or repr cannot print it."""

    __slots__ = ("_v",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("SecretValue needs a non-empty str")
        self._v = value

    def reveal(self) -> str:
        return self._v

    def prefix(self) -> str:
        """The first 8 characters only (the same convention renew_token uses for ids)."""
        return self._v[:8]

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "SecretValue(<redacted>)"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:  # pragma: no cover - trivial
        return "<redacted>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SecretValue) and self._v == other._v

    def __hash__(self) -> int:  # pragma: no cover - trivial
        return hash(self._v)


def looks_like_secret(text: str) -> bool:
    """True when ``text`` could be a credential, key, token id or key material."""
    if _PEM.search(text) or _PREFIXES.search(text):
        return True
    return bool(_LONG_RUN.search(text))
