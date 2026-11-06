# Review PR 833 @7a87c163 (priority 0: Source query links; console board pack link on a locked estate; delta over my BLOCK on d322c43a) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `7a87c163133622840ce4cf915fbcd26d98ce4740`. My BLOCK on d322c43a is lifted: the defect is fixed and I proved the click path in a real browser engine.
Conditions (neither blocks the fix itself): (1) CI and GX10 on the head (docs and static pins pass; I did not run CI). (2) Optional pin gap for a new PR: the 401 branch (secret bar and message) and the network-error branch of the handler are not pinned by any test (mutants H5, H6, H10 survive); I verified them by execution once, not by an automated check.

## The blocking defect is fixed (HIGH, run by me)
The handler no longer calls `g`/`sfetch`/`describe` (function-local to the setup IIFE). The new handler (console.html, first script block) uses only `document.getElementById`, `hdrs` and `$`, all defined at the top level of that block (`function hdrs` at line 778; `$` is a function in the page, measured).
Execution proof, local static server over the head's console.html, real browser engine (in-app browser), `fetch` replaced by a mock and `HTMLAnchorElement.click` intercepted to record downloads:
- `typeof hdrs`, `typeof $` = function; `#secretbar` present.
- 200 answer: click default prevented; status "saved as board-pack.html (17 bytes)"; one download named `board-pack.html` from a `blob:` URL; no unhandled error.
- 401 answer (JSON, "missing or invalid x-field-auth"): status "HTTP 401: the perimeter secret is missing or wrong"; the secret bar displayed; no download.
- 503: status "HTTP 503: the board pack was not served"; no download. Network error (fetch throws): status "could not reach the estate from this browser"; no download. Unhandled rejections: none in any of the four.
- Header: with `SECRET` set to a test value, the request is `GET /attest/pack.html` with `x-field-auth` present, `credentials: same-origin`, and NO operator headers. (Content-Type also rides along on this GET; harmless.)

## Tests (run by me on the exact head, Windows)
- The PR's own: test_board_pack_handler_scope (new, 51 lines), test_board_pack_link_locked_estate, test_render_query_links, test_render_html_escaping.
- My two regression files (copies of the ones I left in the notes folder): the scope test and the 7-test links regression: pass (8 passed in ops-console; 43 passed in attestation-reporter together with the PR's render tests).
- Whole suites on the head: attestation-reporter 307 passed; ops-console 472 passed (includes the innerHTML audit).

## Mutants of the handler (13; counted from the table; against the PR's two ops-console test files plus my scope test)
| # | mutant | result |
|---|---|---|
| H1 | no preventDefault | KILLED |
| H2 | no header (hdrs removed) | KILLED |
| H3 | operator headers sent (hdrs(true)) | KILLED |
| H4 | window.open instead of fetch | KILLED |
| H5 | 401 swallowed, no message | SURVIVED |
| H6 | 401 does not show the secret bar | SURVIVED |
| H7 | non-ok answers not reported | KILLED |
| H8 | wrong download name | KILLED |
| H9 | wrong blob type | KILLED |
| H10 | network error not caught | SURVIVED |
| H11 | pack opened in the console origin (location) | KILLED |
| H12 | link without data-pack | KILLED |
| H13 | wrong click selector | KILLED |
Totals: 13 mutants, 10 killed, 3 survived (10+3 = 13). Part (1) (render `query_cell`) was 9 of 9 killed at the previous head; render.py is unchanged in this delta.

## Delta and identity
- Delta d322c43a..7a87c163: console.html (handler body), a new test_board_pack_handler_scope.py (+51), test_board_pack_link_locked_estate.py (+14/-14); render.py and the attestation tests unchanged.
- Identity: 2 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files; base ede21674, a trial merge into current main was clean at the earlier head and the delta does not touch new files.

## Remaining LOW findings (unchanged from the previous report)
Middle-click and ctrl-click bypass the handler and hit the 401; `pack-status` is overwritten by the 30 s platform refresh; the linked hrefs are the recorded upstream URLs (internal addresses, F-R8-3).

## Not verified
CI/GX10; a real locked estate end to end (my browser check mocked `fetch`; the PR's live check was the builder's); the 30 s timeout path (the new handler uses a plain `fetch`, not `sfetch`, so it no longer has the 30 s abort at all: a hung pack build keeps the status on "fetching the board pack…").
