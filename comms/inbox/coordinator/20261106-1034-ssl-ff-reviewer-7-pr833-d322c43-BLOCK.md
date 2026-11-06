# Review PR 833 (priority 0: Source query links; console board pack link on a locked estate) — ssl-ff-reviewer-7

**VERDICT: BLOCK** on head `d322c43a7dfad208fc4d1626191bf2d53a37c180`.
Part (1), the Source query links, is correct. Part (2), the board pack link, is BROKEN by this change: clicking it throws `ReferenceError` and does nothing. The click is swallowed (`preventDefault`) so the old 401 tab no longer opens either: the link is inert, which is worse than before. Measured in a real browser engine (below). This supersedes my earlier partial note on R-CONSOLE-regression-attestation-links; this is the review of the fix that note was waiting for.

## The blocking defect (HIGH, reproduced by execution)
`services/ops-console/src/ops_console/static/console.html` has TWO `<script>` blocks. The new click handler (`document.addEventListener("click", ..., closest("a[data-pack]") ...`, line 1285) is in the FIRST block. It calls `g(...)`, `sfetch(...)` and `describe(...)`. Those three are defined only in the SECOND block, inside the guided-setup IIFE (`(function () {` at line 1411, `const g` at 1416, `async function sfetch` at 1475, `function describe` at 1495, closing `})();` at 1949), so they are function-local and invisible to the first block (HIGH, read; grep of the first block finds no definition of any of the three).
Reproduction (no secrets; a local static file server over the head's console.html, real browser engine via the in-app browser):
1. serve `services/ops-console/src/ops_console/static/` on 127.0.0.1 and load `console.html`;
2. page console: `typeof g, typeof sfetch, typeof describe` -> `undefined undefined undefined`;
3. insert `<a href="/attest/pack.html" data-pack="html">board pack</a><span id="pack-status">idle</span>` and dispatch a click: `defaultPrevented: true`, the status text stays `idle`, and the page logs an unhandled rejection `g is not defined`; no fetch, no download.
So on any estate (locked or not) the board pack link now does nothing. The PR's own tests (36 attestation-reporter and 5 ops-console tests, all green on the head) are static text pins and cannot see this: the PR says the handler "was not run in a real browser".
Suggested fix (builder's choice): put the handler inside the setup IIFE (where `g`, `sfetch`, `describe` live) or hoist those three helpers to the first block; and add a scope test (below).

## Regression tests (delivered, not pushed; also untracked in my scratch worktree D:\dev-cache\wt-rev7-p833)
In `D:\AppData\Roaming\Claude-bob-the-builder\side-session-notes\local_ac13f221-3c0a-49fe-8f29-87dc83475667`:
- `rev7-test_rev7_board_pack_handler_scope.py` (target `services/ops-console/tests/`): finds the `<script>` block holding the `a[data-pack]` handler and requires every helper it calls (`g`, `sfetch`, `describe`) to be defined at that block's top level. FAILS on d322c43a (`g` is called by the handler but is not defined at the top level of its block); sanity: PASSES (6 passed with the PR's own pin file) once the three helpers are defined at the top level of the first block (throwaway stub, not a fix).
- `rev7-test_console_attestation_links_regression.py` (target `services/attestation-reporter/tests/`): 7 tests, 7 pass on this head: each absolute `GET http(s)://` query is an anchor with a safe scheme, the " ; " list is split, `javascript:`, `data:`, `vbscript:`, `file:` never link, hostile text is escaped, and no bare protected `/attest/` navigation link remains (anchors carrying `data-pack` are excluded and left to the scope test). On the PRE-fix head the same tests failed 2 of 7 (links, bare navigation), as reported in my partial note.

## Part (1) verified (HIGH)
- `render.py` `query_cell`: one anchor per `GET http(s)://...` entry; list split only at "; GET" (a ";" inside a URL is not a break); non-http(s) schemes, relative paths and other verbs stay escaped text; href escaped with `quote=True`; `rel='noopener noreferrer'`, `target='_blank'`; link text is the recorded query; the JSON pack is unchanged (signed bytes untouched).
- My probes: `http://x/a'onmouseover='alert(1)` and `http://x/b"><script>alert(1)</script>` come out with the quote, angle brackets escaped in both href and text; `javascript:alert(1)` is plain text; `a;b=1 ; GET https://h/c` splits into two links with the ";" kept in the first URL.
- Mutants of `query_cell` (9, run against the PR's tests plus my file and the existing escaping tests): 9 killed, 0 survived (split removed, any-semicolon split, any scheme linked, href unescaped, text unescaped, no noopener, no separator, text branch unescaped, no target).
- Tests on the head: test_render_query_links + test_render_html_escaping 36 passed; ops-console test_board_pack_link_locked_estate 5 passed.

## Other findings (LOW, with the fix)
- Middle-click and ctrl-click on the board pack link do not fire `click`; they navigate to `/attest/pack.html` and get the 401 on a locked estate (the link still carries that href).
- `pack-status` sits inside `refreshPlatform`'s innerHTML, which re-renders every 30 s, so a "saved as board-pack.html" note is overwritten on the next refresh.
- The linked hrefs are the recorded upstream URLs (for example 127.0.0.1:8002): readable on the box, dead on a remote browser, and they show internal addresses (reviewer-8 F-R8-3, not new, not fixed here).
- `GET a ;GET b` (no space after the semicolon) is not split; the engine always writes " ; " so this is theoretical.

## Mergeable otherwise
Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Sonnet 5.5 only; .github/: 0 files; 4 files. A trial merge into current main 117469db is clean (base ede21674).

## Not verified
CI/GX10; whole attestation-reporter (300) and ops-console (469) suites (not run by me); a real locked estate (the PR's live check was reported by the builder, not repeated); the 30 s `sfetch` abort.
