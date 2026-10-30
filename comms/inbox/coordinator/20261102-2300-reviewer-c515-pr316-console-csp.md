# C-515 (Lane 9, groomer taking a reviewer card, cloud review, UNVERIFIED on the GX10): PR 316 fix/console-csp-headers-c456 @9b1fb08

VERDICT: PASS WITH CONDITIONS on 9b1fb0843efaa5151fd4600682ef870b4399caca (one commit on main a9dc4f3, author and committer Don Hagell noreply; repo config and tests only). The policy is what the PR says, in both files, and the new tests go red under every mutant I built that changes the policy; two things I could not verify and one test survivor. No finding blocks.

OBJECTIONS FIRST (failure conditions)
1. A policy that is right on paper breaks the page: `default-src 'none'` blocks anything the console loads that the author did not list. I read console.html (1,936 lines): its three icons are `data:` URIs (lines 11-13, allowed by `img-src data:`), the only network call is `fetch(path)` to its own origin (line 836), the one link is `/attest/pack.html` (a navigation, not a subresource), no external host except the SVG namespace string and a loopback literal (lines 11, 791). I found no blocked load. MEDIUM confidence: I did not run a browser; the builder did, once by hand (his note, not a repo test).
2. A header set in Caddy may lose to the upstream: the console stream route sets its own `Cache-Control: no-cache` (ops_console/api.py:489) and passes through the same catch-all. Whether `no-store` replaces it is not shown by any test. I do not know (no caddy here, no `caddy validate`, no curl against a running proxy).
3. The tests read the Caddyfile text, so a header can sit in the right block and be undone later in it. See M15.
4. `script-src 'unsafe-inline'` remains: the policy stops exfiltration to another origin, not script execution. The PR body says so (it names the nonce route as the larger change); I agree it is honest.
Steelman: the change is small, config only, closes the channel-15 gap that C-457's audit does not (a DOM injection could send the operator key to another origin) and fails closed on new origins.

ASSUMPTIONS: main a9dc4f3; PyYAML and pytest installed in a scratch interpreter (public PyPI, nothing added to the repo); the three test files are the ones the PR touches.

REASONING / RESULTS
1. Head fetched from GitHub by branch name; SHA matches the builder's. Merge base is current main (no rebase needed).
2. Tests: test_console_csp_c456.py, test_console_frame_headers.py, test_gb10_caddy_tls.py: 104 passed. Same two older files on main: 56 passed. The WHOLE tools suite was not run here (builder: 3045 passed, 6 skipped; unconfirmed by me).
3. Mutants, 15 of mine on the two Caddyfiles, run with `-x` (first failure stops): RED: drop connect-src; img-src plus https:; no Referrer-Policy (fly); Cache-Control no-cache for no-store (demo); script-src plus unsafe-eval; default-src *; drop frame-ancestors; script-src plus a foreign host; connect-src plus ws:; style-src plus https:; plus form-action *; plus object-src *; plus base-uri *; the whole console header block moved into the /registry handle. SURVIVES: M15, an added `header -Cache-Control` line after the block (59 passed): the tests do not model a later delete in the same handle. LOW (nobody writes this by accident; a reviewer reading the diff sees it).
4. Scope of the headers: only the console catch-all `handle` (demo, fly). `Caddyfile.gb10` imports the demo route map and has no console handle of its own (grep for 8011), so it inherits. The /attest page and the API routes keep their own headers; "every console response" is true, "every response of the origin" is not, and the PR does not claim it.
5. Public-safe: no estate address, flag value, build SHA or deploy status in the diff.

FINDINGS
- F-C515-1 MEDIUM-LOW (unverified, "I do not know"): `Cache-Control: no-store` versus the stream route's own `no-cache`. Run once with caddy: `curl -sI` the console page and the stream route, expect no-store on both; add the result to the PR.
- F-C515-2 LOW (test gap, M15): a later `header -Cache-Control` or `-Content-Security-Policy` in the same handle is not caught.
- F-C515-3 LOW: `caddy validate` was not run on either file (no caddy here, not run by the builder either); syntax is plain but untested.
- F-C515-4 INFO: favicons are `data:` URIs so `img-src data:` suffices; a future `/favicon.ico` file would be blocked by the policy.

CONCLUSION: PASS WITH CONDITIONS on 9b1fb08: run `caddy validate` and one curl for F-C515-1/-3 before the merge (the coordinator's GX10 run can do it, or a reviewer with caddy). Confidence HIGH on the policy text and mutants (run), MEDIUM on "the page still works" (read, not run), LOW on the header-precedence question (not run).
