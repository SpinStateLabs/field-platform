"""Pacing of the console's whole-chain check (``GET /verify`` on the ledger).

The ledger reads its whole chain to answer ``/verify`` and admits one such request at a time. The console builds an
overview every few seconds for each open page, so the check is paced here: one answer is kept and shown until the next
check is due, whatever the number of pages and streams.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

#: at least this long between the end of one check and the start of the next, whatever the first one answered
INTERVAL_S = 30.0
#: the longest wait a ``Retry-After`` is followed for
RETRY_AFTER_MAX_S = 300.0
#: what the section says while the ledger answers "busy"
BUSY = "busy, retrying"


def retry_after_s(raw: str) -> float:
    """The seconds a ``Retry-After`` value asks for, capped; 0 for a value that is not a count of seconds."""
    try:
        value = float(raw.strip())
    except ValueError:
        return 0.0
    return min(value, RETRY_AFTER_MAX_S) if value > 0 else 0.0


class VerifyPacer:
    """Holds the last answer to the chain check and decides when the next one may be asked."""

    def __init__(self, interval: float = INTERVAL_S, clock: Callable[[], float] = time.monotonic):
        self.interval = interval
        self.clock = clock
        self._lock = threading.Lock()
        self._due: float | None = None
        self._answer: dict[str, Any] = {}
        self._verified: Any = None        # the data of the last check that answered 200

    def answer(self, read: Callable[[], tuple[int, Any, str | None]],
               error_text: Callable[[int, Any], str]) -> dict[str, Any]:
        """``available``, ``data`` and ``error`` for the overview. ``read`` returns the status, the body and the
        ``Retry-After`` value (None when absent); it is called only when a check is due, by one caller at a time.
        While that call is running, other callers get the last answer at once; only before there is any answer do
        they wait for it."""
        if not self._lock.acquire(blocking=False):
            last = self._answer           # replaced whole, never changed in place: safe to read without the lock
            if last:
                return dict(last)
            self._lock.acquire()
        try:
            if self._due is None or self.clock() >= self._due:
                status, data, retry_after = read()
                wait = self.interval
                if status == 200:
                    self._verified = data
                    self._answer = {"available": True, "data": data, "error": None}
                elif status == 503 and retry_after is not None:
                    # the ledger said "busy" and when to come back: not a result, so the last one stays visible
                    wait = max(wait, retry_after_s(retry_after))
                    self._answer = {"available": False, "data": self._verified, "error": BUSY}
                else:
                    self._answer = {"available": False, "data": None, "error": error_text(status, data)}
                self._due = self.clock() + wait
            return dict(self._answer)
        finally:
            self._lock.release()
