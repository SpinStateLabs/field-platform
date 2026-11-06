# Review PR 828 (rebuild of 369: per-tier perimeter keys, a read key never authorises a write; C-772) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `d9a78c02c8996e37906960659f40806627716ee2`. HIGH CARE (perimeter authentication).
Conditions: (1) pin the TEMPLATED write-only trailing-control-character case (carry-forward of Q-24 F-Q24-1; mutant B2 below proves it is still unpinned): add `GET /rotate/%0A` (template `/rotate/{rid}`) to the control-character test, before any read key is issued on an estate. (2) CI green and GX10 16/16 on this head (I ran four suites, not all services). (3) Coordinator decision C3 from the PR (order and one resolution for the PR 369 / PR 490 overlap, plus a non-ASCII key test on whichever lands second).

## Objections first
1. The guard judges paths by string while the router dispatches by its own regexes: any spelling gap is a read key reaching a write route; a matcher can only be shown unsound by a corpus, never sound (Q-24 objection 1, still true).
2. A read key authorises every safe-method request NOT on the write-only list; an adopter's state-changing GET that is not listed is open to it. By design and documented (authn.py docstring, FIELD_READ_KEY env row).
3. `FIELD_READ_KEY` (generic) takes effect on EVERY service that calls `authn.install` (the PR's own env doc says all 14, with defaults) for every GET, because no service lists a write-only path yet (grep: 0 callers pass `service=` or `write_only_paths=`). Setting it on an estate is an estate-wide decision with no per-route review behind it.
4. Non-ASCII keys: the old `hmac.compare_digest(str, str)` raised on non-ASCII; the new `_same` encodes (surrogatepass). Behaviour change on that edge; the PR 490 overlap is flagged by the PR.

## Checks (HIGH, run by me)
- Identity: 13 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 13 (the C1 blocker of the old head is fixed); trailers Sonnet 5.5; .github/: 0 files. Base == current main ede21674.
- Rebuild fidelity: the changed (+/-) lines of the whole PR, and of the three commits whose patch-ids differ (commits 2, 4, 11: only docs/ENVIRONMENT.md context moved), are byte-identical to PR 369's (diff of the +/- lines: empty); net patch-id of packages/field-core/src is identical (`6da7c69e6b1b`) on both; 10 of 13 commit patch-ids identical.
- Tests: field-core whole suite on the head: 1662 passed, 2 skipped (matches the PR). `environment_anchors --check`: 0 wrong. Service suites that install authn with defaults: kill-switch 270, delegation-authority 257, federation-broker 191, all passed (the PR ran none).
- My own differential probe on the head (real FastAPI app; write-only entries `/files/{p:path}`, `/mid/{p:path}/tail`, `/rot/{rid}`; 16 spellings each incl. LF, CR, CRLF, TAB, NUL, space, encoded slash, U+2028, backslash): 0 requests reached the app with the read key on a write-only route; read-only control route 200 with the read key; write-only plain route 401.
- Code read: full key unchanged in behaviour; read key only on GET/HEAD/OPTIONS and only when not matching any spelling (URL path and scope path, with and without root_path) of an exact or template entry; the two internal operator routes always write-only; read key equal to the full key refused at install and ignored at run time; read-key-only config refuses every non-safe request.

## Mutants (24 on authn.py vs test_authn_tiers_c772.py + test_authn.py; counted from the table)
| group | mutants | killed | survived |
|---|---|---|---|
| A: methods, write-only bypass, key compare, equal-key, internal paths (A1-A11) | 11 | 10 | 1 (A8) |
| B: matcher: slash, url/scope path, root, templates (B1-B8) | 8 | 6 | 2 (B2, B5) |
| C: service key, dash, no-full-key, constant-time, read headers (C1-C5) | 5 | 4 | 1 (C4) |
Totals: 24 mutants, 20 killed, 4 survived (11+8+5 = 24; 10+6+4 = 20; 1+2+1 = 4).
Survivors: A8 runtime equal-key guard removed: equivalent in effect (an equal key is accepted as the full key either way). B5 single-segment template `[^/]+`->`[^/]*`: stricter (fail closed), harmless. C4 `==` instead of constant-time compare for the full key: a timing property no functional test can see; reviewed by reading only. B2 (URL-path only): REAL, see condition 1. I demonstrated it: with `request.scope["path"]` dropped, my probe lets the read key reach `/rot/{rid}` (write-only) at `/rot/%0A` and `/rot/%0A%0A` (HTTP 200 from the app), so the current code is right and nothing would catch a regression.

## Optional LOWs (new PR)
Lowercase method, a test that pins constant-time compare (e.g. patching `hmac.compare_digest`), a service passing `service=` and `write_only_paths` (Q-24 F-Q24-3: deployment wiring needs its own review before a read key exists on an estate).

## Not verified
CI/GX10; Linux; the other eleven services' suites; behaviour behind a real reverse proxy that rewrites paths; uvicorn's raw-request-line handling of control characters (the test client only).
