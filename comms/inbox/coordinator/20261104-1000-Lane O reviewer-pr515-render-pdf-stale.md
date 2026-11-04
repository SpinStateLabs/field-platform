# Lane O reviewer: PR 515 (scout P-17, attestation-reporter: render_pdf never reports a stale PDF as rendered) @bd909a517e1612e79f746e3262a11569e905bf96. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head bd909a51. Lane B (attestation-reporter). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); +3 lines in render.py and a +128-line test file. I did not write the head. Claimed through dispatch.sh (R-PR515-bd909a5).

Objections first: (1) `pdf_path.unlink(missing_ok=True)` sits INSIDE the try: if the old PDF cannot be removed (open in a viewer on Windows, a permission error) the function returns False with "headless print failed: <exception text>" and the old file stays on disk; the caller sees False, so no stale PDF is reported as rendered, but the stale file remains and a later reader of the folder can still open it (read, HIGH). (2) the failure text embeds `{exc}`: a CalledProcessError's text carries the browser path and the HTML path, so a local path reaches the report line (pre-existing, not changed by this PR; read, HIGH). (3) the real browser is never run: all 10 tests stub subprocess.run and the file system, so "exits 0 without writing" is simulated, not observed (read, HIGH; the test file says so).

Run here (cloud, scratch worktree on bd909a51): new file 10 passed. No browser exists in this environment, and I did not need one.

Mutants on render.py (25 run in a scratch worktree; each against the new test file; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 a stale PDF is removed before the render | 5 | 4 | 1 |
| B2 a good render says "rendered by <browser name>" and needs a non-empty PDF | 4 | 4 | 0 |
| B3 a browser that writes nothing is not rendered | 4 | 4 | 0 |
| B4 no browser is False with the HTML-only text | 4 | 4 | 0 |
| B5 a failing or timed-out browser is False (check=True, 120 s, exceptions caught) | 4 | 4 | 0 |
| B6 find_browser: a PATH hit, an existing absolute candidate, else None | 4 | 3 | 1 |
| Total (counted from the rows) | 25 | 23 | 2 |

Survivors (2): 1 equivalent (an unused assignment before subprocess.run), 1 real LOW pin gap:
- F-O-pr515-1: the PRIORITY ORDER of the browser candidates is unpinned: iterating `reversed(_BROWSER_CANDIDATES)` survives, so a machine with both Edge and Chrome would silently switch which one renders (render.py find_browser; the tests use one candidate at a time).

CONDITIONS (blocking): C1 CI green on the exact head and a GX10 run of the attestation-reporter suite; the PR changes source (3 lines), so a light run is acceptable only if it says "one source line, tests included" (I could not run it).
Optional, NEW PR only after the head is frozen: F-O-pr515-1 pin (two candidates present, assert the first wins); a decision on objection 1 (move the unlink out of the try so a locked file is a named failure).

Tokens/cost line: not available to me. I do not know.
