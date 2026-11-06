# Review PR 624 (S3-4: kill-switch CLI: an unreachable service is one line, ids quoted, verb behaviour tests) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `9fe5a9e0bbbd777e08e45d889d1e2fc94fb4872a` (no conditions beyond the standard CI and GX10 on the landed head). Incident-critical tool (kill, revive, drill), so I probed the failure paths by hand as well as mutating.

## Checks (HIGH, run by me)
- Identity: 3 commits (two work commits and one merge of main), author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 3; trailers Sonnet 5.5 (merge: none); .github/: 0 files. 2 files: kill_switch/cli.py (+57/-18), tests/test_cli_verbs.py (+198). Based on b963407a; main is 250154d3; a trial merge into current main is clean.
- Code read: one `_request` helper for every verb; `httpx.HTTPError` becomes `error: kill-switch unreachable (<ExceptionClass>)` plus, for writes, either "; nothing was changed" (only for errors raised before any bytes reach the service: ConnectError, ConnectTimeout, UnsupportedProtocol) or "; the outcome is unknown: read the agent's status (heartbeat) before you retry" (read timeout, dropped connection); exit 1; never the URL, headers or exception text. `_q` quotes each id as one path segment and refuses `.` and `..` (exit 2, nothing sent). `_killed` turns a non-JSON or non-object 200 into a named exit 1.
- My probes through the real CLI with a mock transport: ids `a/b`, `a?x=1`, `a#f`, `a%2Fb`, `a b`, a space, `é`, a newline and a NUL all go out as one encoded path segment (`/heartbeat/a%2Fb`, `a%3Fx%3D1`, `a%23f`, `a%252Fb`, `%20`, `%C3%A9`, `a%0Ab`, `a%00b`); `.` and `..` exit 2 with nothing sent. Transport failures on kill, revive, domain-kill, checkin and heartbeat for ConnectError, ReadTimeout and RemoteProtocolError: always exit 1, one line, no leak of a URL or a secret placed in the exception text (15 of 15 combinations), and the write note is "nothing was changed" only for ConnectError. A malformed or odd `FIELD_KILLSWITCH_URL` (`http://[bad`, no scheme, empty, `ftp://x`) gives the same one-line error, not a traceback.
- Tests on the exact head (Windows): test_cli_verbs.py plus the rest of the kill-switch CLI tests 72 passed; the whole kill-switch suite 342 passed (the PR says 288; main's suite has grown); tools/tests/test_operator_cli_c2.py 98 passed.

## Mutants (25 on cli.py vs test_cli_verbs.py; counted from the table)
| group | mutants | killed | survived |
|---|---|---|---|
| id quoting Q1-Q10 (unquoted in each of the six builders, `safe="/"`, `..` allowed, `.` allowed, dot refusal exit 1) | 10 | 10 | 0 |
| transport errors T1-T8 (not caught, read-timeout says nothing changed, connect error says unknown, read verb gets a write note, exception text echoed, exit 0, ConnectTimeout / UnsupportedProtocol out of the not-sent set) | 8 | 7 | 1 (T8) |
| 200 body K1-K4 (non-object, non-JSON, killed flag ignored, killed exit dropped) | 4 | 4 | 0 |
| write marking W1-W2 | 2 | 2 | 0 |
| operator pair P1 (the kill request sends no pair) | 1 | 0 | 1 (P1) |
Totals: 25 mutants, 23 killed, 2 survived (10+8+4+2+1 = 25; 10+7+4+2+0 = 23; 0+1+0+0+1 = 2).
Survivor reading: T8 (UnsupportedProtocol reported as "outcome unknown" instead of "nothing was changed") is cosmetic. P1 is NOT caught by this PR's own test file, but it IS caught by the existing tools/tests/test_operator_cli_c2.py (`test_killswitch_cli_env_pair_is_used_on_guarded_verbs`: 2 failed with the mutant), so the operator-pair behaviour the PR says it leaves unchanged is pinned elsewhere in the repository.

## Not verified
CI/GX10; Linux; a live kill-switch.
