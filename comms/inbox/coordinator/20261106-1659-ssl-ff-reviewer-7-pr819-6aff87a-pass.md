# Review PR 819 @6aff87a2 (E1 v2-one-liners; delta over my PASS WITH CONDITIONS on 0fd5f214) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `6aff87a289d487754d3980702b93e607b9c9e4a6`. My condition 2 (the public-repo rule vs estate status; architect ruling 2026-11-06) is met. My condition 1 (the E-gate adversarial review of whether each cited test proves its word, and whether each wording is true) is NOT part of this PASS: it is the separate card R-E-ADV-v2-one-liners, which starts after this PR merges. Plus the standard CI on the head.

## Checks (HIGH, run by me)
- Delta 0fd5f214..6aff87a2: 3 files (v2-one-liners.md 62 lines, check_one_liners.py 23, test_check_one_liners.py 30). 2 commits above main; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files. Main has moved (now e125a878); the PR base is 3804d0b9 and every pinned commit (3804d0b9) is present in this clone.
- Ruling applied: the global line now reads "Estate status is recorded outside this repository; every Enforced word is test/CI-proven; any live status is Declared." Each row's status line is "Declared (estate status is recorded outside this repository)". Reworded qualifiers: DOA roster "unset by default", check-ins "not made by default", rotation "not armed by default - key custody undecided", gateway "not the default deployment", judge "off by default". The checker's GLOBAL_LINE and REQUIRED_QUALIFIERS were changed to match.
- Residual scan (mine, broader than the PR's list): no "both estates", "either estate", "unset on", "no estate", "rotates today", "run pre-v1", "on the GB10", "on Fly", "on both", "each estate" anywhere in the document (0 hits). The remaining mentions are repo facts: `FORCE_GATEWAY_ENFORCE` defaults to 0 (`integration/demo/docker-compose.yml:310` `:-0`, `integration/fly/entrypoint.sh:105` `:-0`: verified); `FIELD_DOA_ROSTER` has no default in the base compose (only the GB10 "required" overlay makes it mandatory: verified); `docker-compose.gb10.yml:140-148` is the network comment block that says canary-agent's only LLM path is the gateway (verified). Whether enforce is armed on any estate is stated as "recorded outside this repository".
- Two citations added (97 distinct cited tests, was 95; none removed): delegation-authority `test_mint_refused_for_unregistered_agent` and `test_revoke_c625::test_a_revoke_while_the_ledger_is_down_is_refused_502_and_the_token_stays_active`; I ran both: 2 passed.
- Checker on the real file: 412/412 checks passed, 0 FAIL. Tests: test_check_one_liners.py 38 passed (was 36): new tests pin the "pinned commit not in the clone" usage error (exit 2 with a fetch hint), that the real file carries none of five estate-status phrases, and that the real file passes the checker (skipped with a reason in a clone lacking a pinned commit).

## Mutants of the delta (6 attempted, 5 applied, run on the 24 tests selected by -k; counted from the table)
| # | change | result |
|---|---|---|
| C1 | missing-commit check removed | KILLED |
| C2 | missing-commit exit 1 instead of 2 | KILLED |
| C3 | fetch hint dropped from the message | KILLED |
| G1 | old global line restored in the checker | KILLED |
| Q1 | DOA qualifier old wording restored | KILLED |
| Q2 | rotation qualifier edit | NOT APPLIED (my search string missed) |
Totals: 6 attempted, 5 applied, 5 killed, 0 survived, 1 not applied (5+1 = 6).

## Notes (LOW)
- The "no estate status" lint pins five phrases; a new estate fact in other words would pass it (my broader scan found none today). A wider list or a review checklist item is a cheap follow-up.
- The checker still proves existence and key mention only, not that a test proves its word: that is R-E-ADV.

## Not verified
CI; the 95 earlier citations were not re-run (unchanged, pinned at 3804d0b9; I ran all 90 distinct tests earlier in this session); the truth of each reworded qualifier beyond the three repo facts above; the E-gate review.
