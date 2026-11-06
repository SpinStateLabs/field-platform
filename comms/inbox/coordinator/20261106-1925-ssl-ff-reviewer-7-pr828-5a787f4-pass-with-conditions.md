# Review PR 828 @5a787f40 (per-tier perimeter keys; C-772; delta over my PASS WITH CONDITIONS on d9a78c02) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `5a787f40b9137ea2fb211e3bb95b9c3b9e7d509e`. My condition 1 (pin the TEMPLATED write-only trailing-control-character case, Q-24 F-Q24-1) is MET. Conditions that remain are about landing, not the code: (1) the head is based on ede21674, main has moved (f7408db5) and a trial merge conflicts in docs/ENVIRONMENT.md: rebase with `tools/environment_anchors.py --fix`; (2) the conflict with PR 839 in authn.py persists (`git merge-tree` of the two heads: content conflict in authn.py): whichever lands second must keep 839's byte rule (`secret_matches`: presented header re-encoded as latin-1, secret as UTF-8) in 828's `_same`; (3) CI and GX10 on the landed head. All three were in my first report (items C2, C3 and the landing-order note); nothing new.

## Checks (HIGH, run by me)
- Delta d9a78c02..5a787f40: one file, packages/field-core/tests/test_authn_tiers_c772.py, +18 lines (a `/rotate/{rid}` route in the test app and one parametrised test). No source change. Identity: 14 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 14; trailers Sonnet 5.5; .github/: 0 files.
- The new test: `test_a_templated_write_only_path_with_a_trailing_control_character_is_still_refused`, parametrised over `%0A`, `%0A%0A`, `%0D`, `%09`, `%0D%0A`: the read key gets 401 on `/rotate/<suffix>` and on `/rotate/abc`, the full key gets 200 on both.
- Mutant B2 re-run on this head: dropping `request.scope["path"]` from the matcher (URL path only) is now KILLED (5 failed, 37 passed); at d9a78c02 it SURVIVED with 41 passed. The opposite mutant B3 (scope path only) is KILLED too (4 failed). That closes the gap I demonstrated with `/rot/%0A` returning 200.
- Tests on the exact head (Windows): test_authn_tiers_c772.py + test_authn.py 46 passed; whole field-core suite 1667 passed, 2 skipped; `environment_anchors --check` 0 wrong rows.
- My other 22 mutants from the first review are unaffected by a test-only delta (the earlier 20 killed / 4 survived stand: A8 and C4 equivalent or untestable, B5 stricter, B2 now killed, so 21 of 24 killed now).

## Not verified
CI/GX10; the other eleven services' suites; behaviour behind a real reverse proxy; uvicorn's raw-request-line handling of control characters.
