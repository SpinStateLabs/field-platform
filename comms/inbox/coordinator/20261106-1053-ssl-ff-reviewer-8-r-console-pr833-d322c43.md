# R-CONSOLE-regression-attestation-links: review of PR 833 (builder-6, B-CONSOLE-attestation-links)
Head reviewed: d322c43a7dfad208fc4d1626191bf2d53a37c180. Base ede21674; main has since moved (117469db), the PR is behind main (not rebased; I did not test the merge).

## VERDICT: BLOCK (the console half does not work in a browser; the board-pack half is sound)

## Blocking finding B-833-1 (HIGH, confirmed by execution): the new board-pack click handler throws ReferenceError, so clicking "board pack" does nothing
`services/ops-console/src/ops_console/static/console.html:1282-1298` (the new `document.addEventListener("click", ...)`) is in the FIRST `<script>` (starts line 743, global scope). It calls `g(...)` (line 1289), `sfetch(...)` (1291) and `describe(r)` (1292). Those three are defined only INSIDE the second script's IIFE: `(function () {` at line 1411 ... `})();` at 1949, with `const g` at 1416, `async function sfetch` at 1475 and `function describe` at 1495. The first script defines `$`, `esc`, `hdrs`, `api` and others but no `g`, `sfetch` or `describe` (grep of lines 743-1403: no definition). Identifiers declared inside an IIFE are invisible to code outside it.
Effect: `ev.preventDefault()` runs first (the navigation is cancelled), then `g("pack-status")` throws. The user sees nothing happen: no download, no status text, and the old behaviour (a link that at least showed the 401 JSON) is gone. So "Attestation pack does not work" is not fixed from the console on any estate, locked or not.
Reproduction (no network, no secrets): `node rev8-console-click-regression.js` run from the repo root with the PR head checked out (file kept in the shared notes folder `rev8-console-click-regression.js`, and in my scratchpad). It loads the page's first script in a node `vm` with a stub DOM, captures the click handler registered on `document`, calls it with a fake event whose `target.closest("a[data-pack]")` returns an anchor. Output on this head: `preventDefault called` then `HANDLER THREW: ReferenceError: g is not defined`. (The second script fails to load in my stub because the harness does not provide the setup JSON; that does not change the result, since the first script's scope cannot see the second script's IIFE locals either way.)
Why the PR's tests did not catch it: `services/ops-console/tests/test_board_pack_link_locked_estate.py` (5 passed) only searches the page text (for example `'sfetch("/attest/pack.html")' in h`); it never runs the handler. Reviewer-7's static regression file would also pass. A text match cannot see a scope error.
Fix direction (for the builder, I do not fix): put the handler inside the IIFE (after `sfetch`), or use the first script's `$`, `hdrs()` and `api`-style helpers; and add a test that RUNS the handler (node vm as in my harness if node is in CI; otherwise move the logic into a function the first script exposes and exercise it).

## Findings that do not block
### F-833-2 MEDIUM (design, confirmed from code and PR text): the Source query links point at the recorded upstream address
`render.py` (new `query_cell`): `href` is exactly the recorded `GET http(s)://...` URL, for example the ledger's own bind address (`http://127.0.0.1:8002/events?...` on an estate, or a compose host). That address is not reachable from a board reader's browser, and the routes need `x-field-auth` on a locked estate, so a click opens a 401 or a connection error (the same class of defect as the console link). My earlier finding F-R8-3 asked for links on the public prefix; the PR body says "text exactly as recorded, href its URL". This satisfies the card wording (anchor, http/https only, `;` list split) but not "a link that works for a board reader". Don decides: accept as is, or map known upstream bases to the estate's public prefix in `render.py` (not in `engine.py`: `source_query` is inside the signed pack bytes).

### F-833-3 LOW (confirmed): the split guard is untested
Mutant "split on every `;` followed by whitespace" (lookahead for `GET` removed) survives; the comment says a `;` inside a URL is never a break, but no test pins it. A URL cannot contain whitespace, so the practical risk is nil.

## What is correct (HIGH, run by me)
1. Identity: 1 commit d322c43a, author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/` (meta check clean).
2. Board-pack rendering (`render.py` `query_cell`): each `GET http(s)://...` entry becomes `<a class='qlink' href=... target='_blank' rel='noopener noreferrer'>`, ` ; `-joined lists split one per line, anything else (other scheme, verb, relative path) stays escaped text; the href and the text are `html.escape`d.
3. Tests on head: test_render_query_links 14 passed; test_render_html_escaping 22 passed; test_board_pack_link_locked_estate 5 passed (the last one is the weak one, see B-833-1).
4. Mutants on `query_cell`, 9 run: 8 killed, 1 survived (counted from table).
| # | Mutant | Result |
|---|---|---|
| L1 | any scheme matches (`\w+:`) | killed |
| L2 | list never split | killed |
| L3 | split on every `; ` | SURVIVED (F-833-3) |
| L4 | href not escaped | killed |
| L5 | link text not escaped | killed |
| L6 | `rel` removed | killed |
| L7 | entries joined with ` ; ` instead of `<br>` | killed |
| L8 | non-link entries not escaped | killed |
| L9 | `target=_blank` removed | killed |
5. Pre-fix reproduction (card item): both defects reproduced on main by me earlier (F-R8-2, F-R8-3) and by reviewer-7. On this head defect 1 (plain-text cells) is fixed; defect 2 (pack link) is replaced by a link whose handler throws.

## Not verified
A real browser (my click check is a node vm run of the page script, not a rendered page); the setup-wizard "Download pack" buttons (they use the IIFE's own `sfetch`, untouched by this PR); CI and the GX10; the merge with current main.

## Conditions to reach PASS
1. Fix B-833-1 so the click handler runs (scope) and add a test that executes it (it must fail on this head and on pre-fix main).
2. Decide F-833-2 (Don) or record that links are for an unlocked, same-host estate only.
New head needs identity re-check and re-review of the console part.
