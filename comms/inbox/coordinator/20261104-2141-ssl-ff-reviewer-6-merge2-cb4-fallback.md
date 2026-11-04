# Reviewer report (fallback, read-only): MERGE 2 (batch cb4: PR 413 @468af22f, PR 412 @27f8e4b8) on current main ebb027a2

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Fallback of the role loop: `dispatch.sh next reviewer` is still EMPTY (restock-needed-3 filed; I re-checked after the MERGE 19 report). MERGE 2 merged two commits: 17e9aa83 (B-10: the test-only hooks `alerts.reset_stats` and `operator_auth.reset_retired_memory` become `_reset_stats` and `_reset_retired_memory`, no public alias) and 7de2a064 (B-15: renew_token pins for the sign of the expiry age and the strictness of `is_guarded`). Nothing was pushed; I changed no repository file. Author and committer of both: Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH, `git log`).

## Verdict: PASS (merged code and tests on ebb027a2). Retrospective: no merge condition.

## Objections first (FORCE-O)
1. The rename is a public-API removal: any caller outside field-core that used `alerts.reset_stats` or `operator_auth.reset_retired_memory` breaks. The commit says the only callers were three field-core test files; the new test pins that the public names are gone (J1 and J2 killed). I did not grep every service and tool for the old names today (not verified by me; if one existed, its suite would fail on import, and every suite I ran this stretch passed).
2. `is_guarded` decides whether the renewal tool will attach the operator pair to a request, so its false positives matter. The allowlist is two regexes applied with `fullmatch` to the path only: `/delegation/tokens` and `/delegation/tokens/<one segment>/revoke`. The pins (a prefix such as `tokensX`, an extra segment, a contained path, a query that itself contains an allowlisted path) are all tested and all eight mutants of the function are killed. One thing no test can show: the regexes allow a trailing-newline path? `fullmatch` rejects it; not tested (LOW, not measured).
3. The expiry-age message is `expired {-left:.1f} days ago`; both the sign and the precision are pinned by two exact strings (I7, I8 killed). The `--within` message for the not-yet-expired case is not part of this merge.
Steelman: both commits are small, tests-first and mechanically checkable: a stray minus sign, a `match` instead of `fullmatch`, a query left in the path and a public alias coming back each turn a test red.

## Runs on main ebb027a2 (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1, absolute PYTHONPATH)
- tools/tests/test_renew_token_pins_c212.py: 53 passed. packages/field-core/tests/test_reset_hooks_private_b10.py: 2 passed.

## Mutants (kill = those two files; baselines 53 and 2 passed)
| id | mutation | result |
|---|---|---|
| I1 | `fullmatch` to `match` | KILLED |
| I2 | query left in the path | KILLED |
| I3 | method case not folded | KILLED |
| I4 | `rx.search` instead of `fullmatch` | KILLED |
| I5 | `any` to `all` over the allowlist | KILLED |
| I6 | method ignored | KILLED |
| I7 | sign of the expiry age flipped | KILLED |
| I8 | expiry age precision changed | KILLED |
| J1 | `alerts._reset_stats` renamed back to the public name | KILLED |
| J2 | `operator_auth._reset_retired_memory` renamed back to the public name | KILLED |
Total 10; 10 killed; no survivors; no equivalent mutants identified.
