From builder-N4: B-S6-4 field-agent ensure_alive stamp, PR 703

Head SHA: f08a4df39d7b90f89765c7292d3f123297636c3f (fix/field-agent-ensure-alive-stamp-s6-4, draft). UNVERIFIED: no GX10, CI not read.

Claim check: scout evidence true on main (agent.py ensure_alive set _alive_at only on success; check()/cross() skip the heartbeat inside heartbeat_max_age) [HIGH]. No open PR or branch touches agent.py ensure_alive (scout-s5-4-liveness-200 is liveness.py; fix/liveness-stale-after-p7 is kill-switch).

Did: agent.py one statement (`self._alive_at = None` before the heartbeat call; set again only on success). New packages/field-agent/tests/test_ensure_alive_stamp_s6_4.py (7): 5 red on main, 2 healthy-path pins green. One mutant (remove the clear): the same 5 red. Existing test_pins_c145.py green.

Ran: field-agent suite 213 passed, 1 failed: test_canary_agent.py::test_the_process_never_exits_on_a_halt fails identically on clean main in this sandbox (baseline, not this change). environment_anchors --check clean; the four tools tests 261 passed (c57 baseline now passes on current main).

Not verified: CI; the canary failure's cause. Decisions needed: none.
