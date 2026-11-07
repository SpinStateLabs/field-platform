# Review R-PR409-5a77aeb: PR 409 (field-agent SDK transport caps the reply bytes it reads; C-642b; STACKED on PR 372)
Head reviewed: 5a77aeb1d778b7af6750d3a0a4a8e60bc494b3d8. The PR's base is the branch fix/upstream-error-field-agent-c642 (head 1b8f9e3f, PR 372's stack); the PR's own delta is 3 commits (2c089ebb the change, fdc2ec85 and 5a77aeb1 tests) and 2 files: `_transport.py` (+36/-3) and a new 157-line test file. `git merge-tree` of this head with its base is clean (tree ec63e706). Against main it conflicts in docs/ENVIRONMENT.md, but only through the stacked 372 commits, not this PR's files; I reviewed the delta over the base.

## VERDICT: PASS WITH CONDITIONS (the cap works; one behaviour the Governor relies on is unpinned)

## Checks (HIGH, run by me)
1. Identity: all 3 delta commits (and the 3 stacked ones) author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`.
2. Code read: `AuthedClient._send` streams each reply (`stream(VERB, url, **kw)`), counts DECODED bytes per chunk against `MAX_RESPONSE_BYTES = 1_048_576`, raises `ResponseTooLarge` with fixed text (the cap value, no body), else rebuilds an `httpx.Response` (status, headers minus content-encoding/length/transfer-encoding, joined content, the request); a client without `stream` gets a post-call size check; `get`, `post`, `patch` all go through `_send`.
3. Tests on head: test_read_cap_c642b 15 passed; whole field-agent suite 219 passed, 1 skipped.
4. Probes (tr409.py, tr409b.py in my scratchpad; MockTransport and a real local socket): exactly the cap passes; cap+1 refused; two 600000-byte chunks refused; a lying huge Content-Length with a small body passes; a 200 MiB gzip bomb (200 KiB compressed) refused; status, JSON, charset, multiple Set-Cookie headers, params, timeout, `json=` all preserved; 204 and 404 behave (`raise_for_status` raises for 404); a follow-redirects client still follows, a non-following one still returns the 302 with its Location.
5. Mutants on `_transport.py`, 17 run: 14 killed, 3 survived (counted from table).
| # | Mutant | Result |
|---|---|---|
| R1 | streaming cap removed | killed |
| R2 | off by one (`>=`) | killed |
| R3 | off by one (cap+1) | killed |
| R4 | cap 2 MiB | killed |
| R5 | count only the last chunk | killed |
| R6 | check after the loop instead of per chunk | killed |
| R7 | framing headers kept on the rebuilt response | SURVIVED |
| R8 | fallback size check removed | killed |
| R9 | fallback loosened (2x) | killed |
| R10 | `post` bypasses the cap | killed |
| R11 | `patch` bypasses the cap | killed |
| R12 | `get` bypasses the cap | killed |
| R13 | request not attached to the rebuilt response | SURVIVED |
| R14 | headers dropped | killed |
| R15 | status code wrong | killed |
| R16 | refusal text gains extra non-body text | SURVIVED (weak mutant: the text still carries no body; the test pins "no body bytes", not the exact text) |
| R17 | refusal text drops the cap value | killed |

## Conditions
### C1 (MEDIUM): no test pins that the rebuilt response carries its request (R13), and the Governor needs it
`services/conformance-sentinel/src/conformance_sentinel/governed.py:94` calls `resp.raise_for_status()` on the reply of the agent's sentinel client, which is this wrapped transport. `httpx.Response.raise_for_status()` raises `RuntimeError` when the response has no request. With `request=resp.request` removed, the 15 tests still pass, so a regression would break every governed action (a RuntimeError instead of a verdict or an HTTP error) with nothing red. Fix: one test that calls `raise_for_status()` on a 200 (returns) and a 404 (raises `HTTPStatusError`) through `AuthedClient`.

## Observations (LOW)
- R7: the framing headers are dropped by the code but no test checks it; with them kept the body is not double-decoded in my reading of httpx (content is passed directly), so low impact; a header-list assertion would pin it.
- The rebuilt response is not the original: `resp.elapsed` raises `RuntimeError`, `resp.history` is empty, `extensions["http_version"]` is None (probe). No caller in field-agent or the Governor uses them (grep), so no break today; a future caller that times a call with `.elapsed` would fail.
- The cap bounds what is KEPT, not transient memory: a 1 GiB bomb in 1 MiB of gzip over a real local socket peaked at about 149 MB (tracemalloc) before the refusal; the same body as one MockTransport chunk peaked at 459 MB. Bounded by the decoder's per-chunk expansion, not by the cap. A peer-side time bound (slow body) is unchanged (client timeout).
- Stack: this PR lands after PR 372; its own checks above are against 372's head (1b8f9e3f). If 372 changes, rerun the read-cap tests.

## Not verified
Whole-repo suites; GX10 16/16; CI; PR 372 itself (not part of this card).

## Conditions to reach PASS
C1 in a new commit (one test); identity re-check of the new head.
