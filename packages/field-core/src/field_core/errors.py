"""Messages that cross a service boundary (C-503, design note C-490).

A reply from another service is untrusted text: it can quote a value the caller sent, it can be arbitrarily large, and
a client that copies it into an exception message hands it to whoever receives that exception (an HTTP reply, a CLI
line, a ledger or log record). ``upstream_error`` returns only a fixed phrase and the status code. The body goes to a
DEBUG log record, truncated, as an escaped single line; it is never part of the message.

No redaction is done on the debug record: nothing here knows what a secret looks like, so the record stays at DEBUG
(not emitted by the default logging configuration) and a deployment that turns DEBUG on for ``field_core.upstream``
accepts that an upstream's words can appear there.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("field_core.upstream")

#: Characters of an upstream body kept for the DEBUG record.
BODY_LOG_LIMIT = 200


def upstream_error(resp: Any, what: str) -> str:
    """``f"{what} returned {status}"`` and nothing else; the body (first ``BODY_LOG_LIMIT`` characters, escaped, one
    line) is written to the ``field_core.upstream`` logger at DEBUG."""
    status = getattr(resp, "status_code", None)
    # only a real integer status is formatted: an object whose status_code is text could otherwise carry a body
    status = int(status) if isinstance(status, int) and not isinstance(status, bool) else None
    if log.isEnabledFor(logging.DEBUG):
        try:
            body = str(resp.text)
        except Exception:                       # a body that cannot be decoded is not worth an error of its own
            body = "<unreadable>"
        log.debug("%s returned %s; body (first %d characters): %s", what, status, BODY_LOG_LIMIT,
                  ascii(body[:BODY_LOG_LIMIT]))
    return f"{what} returned {status}"
