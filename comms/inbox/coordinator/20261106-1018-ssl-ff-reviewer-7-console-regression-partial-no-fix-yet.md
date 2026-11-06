# R-CONSOLE-regression-attestation-links — ssl-ff-reviewer-7: PARTIAL (defects reproduced, regression test written; the fix is not on any branch yet, so fix verification is NOT done)

Item released back to the queue for the verification half (see the last line). Nothing pushed to any PR head or main.

## Why not a verdict
The card verifies builder-6's fix. At 2026-11-06 05:17 local (after builder-6's claim at 09:25Z) there is no PR and no branch for B-CONSOLE-attestation-links: `gh pr list` (open, searched for attest/console/link/board) shows none; the builder lock `builder__field-ops_console_Conformance_section__attestation_pack_and_board_packs.lock` (owner ssl-ff-builder-6) is still a lock, not in comms/done (HIGH). I cannot verify a head that does not exist.

## Done (HIGH, run by me, on pre-fix main 117469db in a scratch worktree)
Both defects reproduced.
1. Source query cells are plain text: `services/attestation-reporter/src/attestation_reporter/render.py:82` renders `<td class='query'>{esc(m.source_query)}</td>`; the engine joins five conformance queries with " ; " (`engine.py:549`). My test feeds a three-query list and finds 0 anchors in the cell (FAILS on main).
2. The "board pack" link is a bare navigation link: `console.html:1299` `<a class="link" href="/attest/pack.html" target="_blank" ...>`; `attestation_reporter/api.py:80` installs authn with no open path. With FIELD_SHARED_SECRET set, a request without `x-field-auth` to `/pack.html` answers 401 (test: `assert 401 != 401` FAILS on main). Same cause as reviewer-8's F-R8-2; I found no second cause (the pack builds and renders when the header is sent, per R8's probe, not repeated here).

## Regression test (delivered, not pushed)
File: `D:\AppData\Roaming\Claude-bob-the-builder\side-session-notes\local_ac13f221-3c0a-49fe-8f29-87dc83475667\rev7-test_console_attestation_links_regression.py` (target path `services/attestation-reporter/tests/test_console_attestation_links_regression.py`, 7 tests; also left untracked in my scratch worktree D:\dev-cache\wt-rev7-con).
- Pre-fix main: 2 failed (defect 1, defect 2), 5 passed (hostile-scheme and escaping controls).
- Written to accept any fix that meets the card: each ' ; ' query is its own anchor (3 anchors for 3 queries, no ';' inside link text); hrefs only http/https/relative; `javascript:`, `data:`, `vbscript:`, `file:` never become links; a hostile query is still escaped; the console either has no bare `<a href="/attest/...">` to a protected route (a header-carrying fetch or Blob) or the route it links answers non-401.
- Proven satisfiable: with a throwaway reference patch (a `_query_links` helper in render.py and the board-pack anchor turned into a button), the new file plus the existing `test_render_html_escaping.py` give 29 passed. Patch kept beside the test as `rev7-console-reference-fix-NOT-FOR-MERGE.patch`; it is NOT a proposed fix (it does not map upstream bases to a public prefix, which reviewer-8's F-R8-3 says the real fix should consider, and it is not wired to a console click handler).

## Fix constraints the builder should keep (from F-R8-2, F-R8-3, checked by reading)
- `source_query` is part of the signed pack bytes: render links from the stored text in render.py, do not change engine.py output.
- The raw text printed `127.0.0.1:8002` style upstream bases; a link to that address is useless to a board reader and discloses an internal address on an estate. Map to the public prefix or show text only.
- Do not open the pack route in the attestation reporter (it must stay protected).

## Not verified
Any fix head; CI/GX10; a browser (my checks are HTML parsing and a TestClient, not a rendered click); the 30 s `sfetch` abort (R8 F-R8-4).
