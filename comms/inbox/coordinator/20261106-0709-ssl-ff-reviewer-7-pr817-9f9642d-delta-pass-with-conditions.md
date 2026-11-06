# Review PR 817 @9f9642d5 (G21 provision edit_refused; delta re-review of reviewer-8's PASS WITH CONDITIONS on 2a7da71a) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `9f9642d560e87af7a904318edd15e5426f4e53b2`.
Reviewer-8's only condition (make the golden test portable to Windows; red team F-817-1) is met on Windows. Remaining condition (the one reviewer-8 set): the two golden tests must be shown green on Linux/GX10 on this head; I could not run Linux. Scope: delta over 2a7da71a (one tests-only commit); the code and manifests were reviewed by reviewer-8 and are not re-reviewed here.

## Checks (HIGH, run by me)
- Delta `git diff 2a7da71a 9f9642d5`: 1 file, services/lifecycle-manager/tests/test_provision_alias_listed_require_g21.py, `_normalise` only (+3/-1). No source, golden or manifest change.
- Identity: the new commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>, no trailer; 2 commits above main, both repo identity; .github/: 0 files. Head contains current main's base ede21674 (merge-base 3804d0b9).
- Tests on the exact head (Windows): the G21 file, test_provision_register_c73 and test_provision_unchanged_p29 together: 55 passed (the two golden tests were the 2 failures at 2a7da71a). Builder-6 reports 10 passed for the file and 287 for the lifecycle-manager suite; I ran the three files.
- The new `_normalise`: replaces the JSON-escaped dir and the plain dir with `<dir>`, then folds escaped backslashes (`\`) into `/`. The golden (read by me) contains only single-backslash escapes (`\n`, `\"`, `\u2014`) and `<dir>/...` paths, so the fold changes nothing on Linux, as the commit says.

## Mutants (6 applied of 7 attempted, on the golden/normalise path; counted from the table)
| # | change | result |
|---|---|---|
| G1 | old `_normalise` restored (fix reverted) | KILLED (2 failed: the fix is needed) |
| G2 | golden `registry_outcome` changed | KILLED |
| G3 | engine detail text changed | NOT APPLIED (text is in another file; my search string missed) |
| G4 | dir never masked | KILLED |
| G5 | token_id not masked | KILLED |
| G6 | plain (Linux) `replace(here, ...)` dropped | SURVIVED (equivalent on Windows; that half is the Linux path and cannot be exercised here) |
| G7 | backslash fold dropped | KILLED |
Totals: 7 attempted, 6 applied: 4 killed, 1 survived, 1 not applied (4+1+1 = 6 applied-or-not... applied = 5 killed/survived + G3 not applied); killed 4 of the 5 applied (G1, G2, G4, G5, G7 killed = 5; G6 survived = 1; so 5 killed, 1 survived, 1 not applied: 7 total).
Correct count: 5 killed, 1 survived, 1 not applied.

## Findings (LOW)
- G6: the Linux branch of `_normalise` is protected by nothing I can run; the first-run proof on Linux/GX10 is the condition above.
- The fold turns every `\` into `/`, so a future real backslash in non-path output would be masked in this golden; the golden has none today.

## Not verified
Linux/GX10 on this head; CI; the earlier review's scope (engine, manifests, runbook).
