# Reviewer report: PR 595 @ 37cec4cfd4fa6aadb0a52a23ca6535cb9f8ea0c2 (tools/start_role_session.py hardening, scout S-2-12)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). One commit on origin/main b963407a (the current tip, which already carries PR 546's no-proxy, no-redirect opener); `git merge-tree --write-tree origin/main pr595` clean (HIGH). 3 files (+199/-6): tools/start_role_session.py (+20/-6), tools/tests/test_start_role_session.py (4 lines), tools/tests/test_start_role_session_hardening.py (+175). Author and committer Don Hagell 13129187+dhagell@users.noreply.github.com, trailer Sonnet 5.5 (HIGH).

## Objections first
1. The session id from the first reply is interpolated into the URL of the second call (`/v1/sessions/{sid}/events`). The PR now requires a non-empty string, but not a path-safe one: an id containing `/`, `..`, `?` or `#` would redirect the second request (which carries the API key header) to another path of the same host. The host is fixed and the reply comes from the real API, so the exposure is small (read from the code, not run, MEDIUM-LOW); a one-line pattern or `urllib.parse.quote(sid, safe="")` would close it, and none of the 19 mutants below touches it.
2. The upper bound of 100,000,000 cents (1,000,000 USD) is a typo guard, as its comment says, not a spending policy; the workspace budget is the real limit. A number typed with a stray zero below the cap is not caught. Accepted as stated.
3. The tool sends a workspace API key; the prior PR (546) made the opener proxy-free and redirect-free. This PR keeps that opener (read) and adds error handling around it; the redirect and proxy pins stay in PR 546's tests, which I ran with this head (51 passed in the two start_role_session test files).

## Verified (run by me)
- Baseline on the exact head: tools/tests/test_start_role_session.py + test_start_role_session_hardening.py 51 passed; with the C-57 proxy lint file 153 passed (relative PYTHONPATH `tools`).
- Code read: `_budget_cents` accepts only ASCII digits, a value from 1 to MAX_BUDGET_CENTS, and sends the canonical integer text (leading zeros dropped); an HTTP error prints the status and a fixed phrase, never the body; transport errors and non-JSON replies exit with the exception class name only; a reply without a usable string id exits before the second request.

## Mutants (mutations of tools/start_role_session.py; scratch worktree on the head; baseline 51 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| B1 | non-ASCII digits accepted | 1 failed | yes |
| B2 | non-digit text accepted | 2 failed | yes |
| B3 | zero accepted | 1 failed | yes |
| B4 | cap off by one (`<=` -> `<`) | 1 failed | yes |
| B5 | cap raised tenfold | 1 failed | yes |
| B6 | value sent as typed (leading zeros kept) | 1 failed | yes |
| B7 | budget type not applied to the option | 14 failed | yes |
| B8 | default budget changed | 1 failed | yes |
| H1 | HTTP error prints the upstream body | 9 failed | yes |
| H2 | HTTP error drops the status | 10 failed | yes |
| T1 | transport error prints its text | 6 failed | yes |
| T2 | OSError not caught | 6 failed | yes |
| T3 | ValueError (bad reply) not caught | 4 failed | yes |
| T4 | transport error no longer exits | 6 failed | yes |
| I1 | reply without an id not refused | 8 failed | yes |
| I2 | empty id accepted | 1 failed | yes |
| I3 | non-string id accepted | 1 failed | yes |
| I4 | non-dict reply raises instead of a refusal | 3 failed | yes |
| I6 | prints `s['id']` instead of `sid` | 51 passed | NO (equivalent: the same value once the id check has passed) |
Totals counted from the table: 19 valid mutants, 18 killed, 1 survived (I6, equivalent). My I5 (id check after the event) did not build and is excluded. No other survivor to run against the suite.

## Findings
- F-S212-1 MEDIUM-LOW: objection 1, an unvalidated session id is placed in a request path; validate or quote it, and pin it.
- F-S212-2 LOW: I6 is equivalent, nothing to do.

## Verdict: PASS on 37cec4cfd4fa6aadb0a52a23ca6535cb9f8ea0c2
Head frozen; F-S212-1 goes in a NEW PR (it is not a defect of anything the PR claims). CI green and the full GX10 run on this exact head per the coordinator procedure (code and tests, so no light run). Not run by me: CI, GX10, the real API.
