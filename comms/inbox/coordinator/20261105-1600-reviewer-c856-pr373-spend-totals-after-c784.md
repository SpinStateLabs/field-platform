VERDICT: PASS WITH CONDITIONS on 8c3cfb5eb833ff482d7050409327872ffab93812
(Lane 14, cloud, no GX10: UNVERIFIED re-run. PR 373, spend-governor `/totals`: two commits on main (2f7450a the 422 fix, 8c3cfb5 the time-zone test fix); author and committer Don Hagell no-reply on both; two files (+166 -5): services/spend-governor/src/spend_governor/api.py and tests/test_reaudit_c616.py. Ran here at this head: the whole spend-governor suite, 279 passed, 0 skipped (not the 16-suite GX10 set). CI at this head: see the last line. Reads Lane 15's C-784 on 2f7450a (PASS WITH CONDITIONS C1-C3).)

OBJECTIONS FIRST
1. The card names the "status-only error rule" (an error is a fixed phrase plus a status, never caller text). This endpoint echoes the caller's own `since`, unbounded, in its 422; so the rule is not followed here.
2. A boundary table is only as good as its probes; I ran my own instants rather than the PR's list.
3. Whether a test "pins" a bound is shown by removing the bound; I removed each one.

ASSUMPTIONS
A1. Python 3.13 in this sandbox (`datetime.fromisoformat` of 3.11+ semantics; the service requires 3.11 or newer). A2. The app is driven in process with an injected clock and a scratch store; one capped agent; no network.

REASONING: C-784 CONDITIONS AT 8c3cfb5
1. C1 (the host time-zone test never ran because `os.tzset` does not exist): CLOSED. The skip is now `not hasattr(time, "tzset")` (tests/test_reaudit_c616.py, the `test_a_naive_since_is_read_as_utc_in_any_host_time_zone` decorator); the four cases (America/Toronto, Asia/Kolkata, Pacific/Auckland, UTC) run and pass here (4 passed, 0 skipped); the suite is 279 passed, 0 skipped. Mutant: the naive-as-UTC line replaced by `pass` goes RED (it survived at 2f7450a). HIGH (run).
2. C2 (echo of `since` in the 422): OPEN, decision. The handler (api.py, `/totals`) raises `HTTPException(422, f"since {since!r} is not an ISO 8601 instant")`. Probe: a 3,000-character value containing `<script>` is returned in full (3,073 bytes), JSON-escaped (no injection; control characters appear as escapes). So the status-only rule is not followed here. The same handler's 404 echoes the path parameter `agent_id`. Neither is pinned: the mutant that replaces the echo with fixed text stays GREEN, so a later change either way is silent. LOW-MEDIUM, non-blocking. HIGH (run).
3. C3 (a mutant per remaining bound): done by me: OverflowError no longer caught (overflow becomes a 500) RED; naive instant not read as UTC RED; offset not converted to UTC RED; status 422 changed to 400 RED; naive/aware condition inverted RED; 5 of 5 RED. One more, not asked: `since.strip()` before parsing stays GREEN (a space-padded instant is refused today and nothing pins that) (F-C856-2, LOW).
THE CARD'S OWN QUESTION: INSTANTS, probed (34 spellings, scratch app):
 - Minimum: `0001-01-01T00:00:00` naive and `...Z` 200 (read as UTC); `0001-01-01T00:00:00-05:00` 200 (UTC 05:00); `0001-01-01T00:00:00+05:00` 422 (its UTC conversion leaves year 1): the overflow case the PR exists for. 
 - Maximum: `9999-12-31T23:59:59.999999` naive and `Z` 200; `...+05:00` 200 (UTC 18:59:59); `9999-12-31T23:59:59-05:00` 422 (overflow); never a 500. 
 - Epoch and before: `1970-01-01T00:00:00Z`, `1970-01-01`, `1969-12-31T23:59:59Z`, `1970-01-01T00:00:00-00:01`: 200, correct UTC. A numeric epoch ("0", "1000000000") is 422 (not an ISO instant), "now" 422, empty 422.
 - Naive versus aware: a naive instant is UTC in every host zone (the four-zone test); an aware instant is converted; offsets up to `+23:59` accepted, `+24:00` 422; an offset with seconds (`+05:30:15`) accepted and converted (3.11+ behaviour, harmless).
 - Format edges: space instead of `T` 200, ISO week date (`2026-W44-5`) 200, basic format (`20261030T120000Z`) 200 (all Python 3.11+ behaviour: below 3.11 they would be 422; the service floor is 3.11); lower-case `t` or `z` 422; year 0000 and year 10000 422; non-leap Feb 29, second 60, hour 24 422; NUL, Arabic-Indic digits, padding spaces 422. A 5,000-character garbage value 422.
 - The 422 versus 404 order: an unknown agent gets 404 before `since` is looked at.
 HIGH (run).
STATUS-ONLY ERROR RULE (the card's last ask): the neighbouring 422s and the new overflow 422 share the echo; this PR keeps that wording and adds a second path to it (OverflowError). If the rule is to apply (as PR 326's helper applies it to upstream bodies), this handler needs fixed text for both 422 and 404; the choice belongs to the card owner (C2).
Public repo: no estate address, flag value, build SHA, deploy status or credential in the diff; probes used a scratch store and a fake agent id. HIGH.

FINDINGS
F-C856-1 (LOW-MEDIUM, OPEN, carried C-784 C2): api.py `/totals` echoes the raw `since` (unbounded) in the 422 and `agent_id` in the 404; not pinned either way.
F-C856-2 (LOW, new): a space-padded `since` is refused today but nothing pins it (strip mutant GREEN).
F-C856-3 (INFO): the accepted formats (ISO week, basic, space separator, offsets with seconds) depend on the Python version; the service floor is 3.11, where they hold; a test pinning "version floor" or a stricter parser would make the contract explicit.
CLOSED at this head: C-784 C1 (time-zone test now runs; naive-as-UTC mutant red), C3 (each bound has a red mutant).

CONDITIONS
C1 (non-blocking): the echo decision (F-C856-1), with a test whichever way it goes.
C2: the CI result at this head, and the GX10 run.
Not verified: CI (below); Python versions other than 3.13; the 16-suite GX10 set; the consumers of `/totals`.

CONCLUSION
Lane 15's C1 and C3 are closed in code (the time-zone cases run and kill the naive-as-UTC mutant; every bound I removed turns the suite red), and the instant table is clean: the overflowing instants at both ends are 422 and nothing I sent produced a 500. The echo of the caller's value in the 422 remains, unpinned, which is the status-only rule's question. PASS WITH CONDITIONS (non-blocking) on 8c3cfb5.

CI at 8c3cfb5, read by REST: tests (3.12) queued null; tests (3.14) queued null; tests (3.13) queued null; tests (3.11) queued null; fly-image-smoke completed success; compose-smoke completed success; compose-upgrade-smoke completed success
