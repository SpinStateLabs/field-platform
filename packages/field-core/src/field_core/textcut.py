"""Shorten free text without splitting an id.

``cut(text, limit)`` is ``text[:limit]``, except when the limit falls inside a dashed UUID-shaped run (the form of the
platform's ids): then the text is cut before that run. An id therefore leaves whole or not at all. Clean or collapse a
text BEFORE passing it here; a later step that shortens it again must use this too.
"""

from __future__ import annotations

import re

UUID_SHAPED = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
ID_LENGTH = 36


def cut(text: str, limit: int) -> str:
    """At most ``limit`` characters of ``text``, never ending inside a UUID-shaped run."""
    if len(text) <= limit:
        return text
    end = limit
    start = max(0, end - ID_LENGTH + 1)
    while start < end:                     # a run starting here would reach past ``end``
        if UUID_SHAPED.match(text, start):
            end = start
            start = max(0, end - ID_LENGTH + 1)       # the new end may fall inside an earlier, overlapping run
        else:
            start += 1
    return text[:end]
