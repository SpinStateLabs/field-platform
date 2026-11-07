"""C-1014 port, item (c) (reviewer F-C869-8): the SDK runs tool calls on threads, so RateLimiter.allow is called
concurrently. The check and the record must be one step. The test widens the gap between them (the record sleeps) so a
limiter without a lock lets more than the limit through. Mutant: L1 the lock is not taken."""
import threading
import time
from collections import deque

from field_mcp import audit as au


class SlowDeque(deque):
    def append(self, x):
        time.sleep(0.01)                 # the window between "count < limit" and "recorded"
        super().append(x)


def test_concurrent_calls_never_exceed_the_limit():
    rl = au.RateLimiter(2, lambda: 0.0)
    rl._hits = SlowDeque()
    allowed, start = [], threading.Barrier(16)

    def worker():
        start.wait()
        allowed.append(rl.allow())

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(allowed) == 2 and len(allowed) == 16
