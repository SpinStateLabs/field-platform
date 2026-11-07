# Delta review PR 699 (S5-21 force-gateway real_upstream named 502) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `f46c79a5b3eae16deb002b3d28962146c253167a` (delta from my earlier review at 516d9cbb; its condition C1, a valid-JSON body that is not an object, is CLOSED).
Conditions: C1 pin `from None` on the transport-error raise (mutant B5 survives; non-blocking, can follow). C2 CI and GX10 on the landed head (Linux not verified).

## Checks (HIGH, run by me)
- Identity: the 3 PR commits (efcf22bb, 516d9cbb, f46c79a5) author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Sonnet 5.5; 0 files under .github/. 3 files: api.py (+23/-11), test_real_upstream_transport.py (+166), docs/ENVIRONMENT.md (+10/-10).
- Trial merge with main 41afda502 (base b963407a): clean. `environment_anchors.py --check`: 0 wrong anchor rows.
- Delta code: the `isinstance(answer, dict)` guard raises 502 "upstream answered JSON that is not an object (status N)" (status only, no body, no URL, no key); `{}` still passes through. Transport errors give 502 with the class name only; non-JSON gives 502 with the status.
- Tests on exact head (Windows, Python 3.14): 34 passed (the PR's 9 grew to 34 across the two later commits). I did not re-run the whole force-gateway suite (PR reports 457 passed at its first head).
- Own probe of real_upstream with odd base URLs: spaces in host, ftp scheme, empty, `http://:80`, closed port all give 502 with a class name only (ConnectError / UnsupportedProtocol). `http://[::1` raises a RAW `ValueError: Invalid IPv6 URL` (a 500 at the route): it comes from the existing urlparse in the plain-http warning, BEFORE the new try block, so it is outside this PR; the message carries no key. MEDIUM that it is pre-existing (I did not run main).

## Mutants (14; counted from the table)
| # | mutant | result |
|---|---|---|
| B1 | HTTPError not caught | KILLED |
| B2 | narrowed to ConnectError | KILLED |
| B3 | message echoes exception text | KILLED |
| B4 | transport status 500 | KILLED |
| B5 | `from None` -> `from exc` (cause chain kept) | SURVIVED |
| B6 | non-JSON ValueError not caught | KILLED |
| B7 | non-JSON status dropped | KILLED |
| B8 | non-dict check removed | KILLED |
| B9 | non-dict check only some types | KILLED |
| B10 | empty dict refused | KILLED |
| B11 | secret scrub removed | KILLED |
| B12 | upstream status replaced | KILLED |
| B13 | anthropic-version not forwarded | KILLED |
| B14 | timeout changed | KILLED |
Totals: 14 attempted, 13 killed, 1 survived (13+1 = 14), 0 not applied. B5 matters only to logs and tracebacks (the chained httpx error can hold the URL), LOW.

## Not verified
CI/GX10; Linux; whole force-gateway suite on this head; the IPv6 ValueError path on main.
