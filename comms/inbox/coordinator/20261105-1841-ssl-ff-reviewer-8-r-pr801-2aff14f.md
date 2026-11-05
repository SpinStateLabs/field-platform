# Review R-PR801-2aff14f — PR 801 (public safety: paths and mailboxes, guard test; rebuild of #342/#797)
Head reviewed: 2aff14f21e86162efda8f6d5b3448ec23a60c3c8. Base 869cf2ed (main has since moved; merge-base check only, rebase not re-tested).

## VERDICT: PASS (both #797 BLOCK findings are fixed)

## #797 BLOCK findings
1. Identity: all 17 commits (merges included) author AND committer Don Hagell 13129187+dhagell noreply; no mismatch line from `git log` (HIGH). The non-canonical dhagell@users.noreply.github.com commits are gone.
2. .github/: net diff vs base touches nothing under .github/ (HIGH). The ci.yml comment edit is gone; the untouched comment is instead counted in the allowlist.

## Content
3. Net content vs #797 head e4ea5559 (each against its own base), changed lines `-U0`: same 24 files, identical changed lines except two added allowlist entries: `.github/workflows/ci.yml::unix-home-path = 1` (functional) and `services/sealed-ledger/tests/test_witness_url_scrub.py::userinfo-url = 6` (fixture), as the PR body says (HIGH).
4. Tests on head: test_public_safety_c560 410 passed; windows_pins_without_powershell_c726 13 passed; operator_mounts_b6 19 passed; field_rest_secret 26 passed, 9 errors ("harness exited early"), identical 26/9 on the base 869cf2ed, so environmental (HIGH).
5. Mutants on the scanner in test_public_safety_c560.py (run without the full-repo scan test): 15 run, 15 killed (counted from table).
| # | Mutant | Result |
|---|---|---|
| 1 | mailbox_allowed always True | killed |
| 2 | OWN_DOMAINS drops .com | killed |
| 3 | RESERVED_TLDS empty | killed |
| 4 | NOT_PERSONAL_LOCALS empty | killed |
| 5 | GENERIC_ACCOUNTS entry "runner" renamed | killed |
| 6 | hex private: 10/8 -> 11 | killed |
| 7 | hex private: 192.168 -> 192.169 | killed |
| 8 | stale check `<` -> `<=` | killed |
| 9 | new-site check `>` -> `>=` | killed |
| 10 | MIN_REASON 20 -> 1 | killed |
| 11 | sandbox hostname exemption removed | killed |
| 12 | URL-userinfo overlap exemption removed | killed |
| 13 | `moves:` not tolerated | killed |
| 14 | CGNAT lower bound 64 -> 65 | killed |
| 15 | stale entries ignore `scanned` | killed |
6. Not verified: regex classes beyond those mutants; the full-repo scan test was run unmutated only (passes); GX10 16/16; current main (it moved after base 869cf2ed): a rebase may change allowlist counts and the repository scan, so the landing run must be on a head rebased onto current main.

## Conditions
1. Before landing, re-run test_public_safety_c560 on the head as rebased onto current main (allowlist counts are exact in both directions); any count fix goes in a new commit and needs a fresh identity check.
Head frozen at 2aff14f2.
