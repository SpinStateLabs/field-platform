"""Messages that cross a service boundary (C-503, design note C-490).

A reply from another service is untrusted text: it can quote a value the caller sent, it can be arbitrarily large, and
a client that copies it into an exception message hands it to whoever receives that exception (an HTTP reply, a CLI
line, a ledger or log record). ``upstream_error`` returns only a fixed phrase and the status code.

The body is never logged either (Backlog B4): nothing here knows what a secret looks like, and an upstream that echoes
a header or a request value would put it in any record that quoted it. The DEBUG record on ``field_core.upstream``
names the status and the body's length only.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("field_core.upstream")


def upstream_error(resp: Any, what: str) -> str:
    """``f"{what} returned {status}"`` and nothing else. The ``field_core.upstream`` logger gets a DEBUG record with
    the status and the body's length in bytes, never the body itself (Backlog B4)."""
    status = getattr(resp, "status_code", None)
    # only a real integer status is formatted: an object whose status_code is text could otherwise carry a body
    status = int(status) if isinstance(status, int) and not isinstance(status, bool) else None
    if log.isEnabledFor(logging.DEBUG):
        try:
            size: object = len(resp.content)
        except Exception:                       # no bytes to count is not worth an error of its own
            size = "unknown"
        log.debug("%s returned %s; body withheld (%s bytes)", what, status, size)
    return f"{what} returned {status}"
