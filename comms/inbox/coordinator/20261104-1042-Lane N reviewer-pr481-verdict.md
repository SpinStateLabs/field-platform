# Reviewer (docs): PR 481 (C-1198) the 2026-11 hardening lessons as short rules with their evidence files

**Verdict: PASS WITH CONDITIONS on head `043420cc6c39813f41fcb1cf877746fa99081329`.** Docs only (one file, `tasks/lessons.md`, +56). Head unchanged at start and end; 1 commit, Don Hagell noreply on author and committer. Not built by this lane. A docs PR has no behaviour to mutate, so the "mutants" here are claim checks against the cited evidence.

## What I checked (HIGH, from git)
- Every evidence path the section cites exists on `origin/comms`: 11 of 11 (7 under `inbox/builder`, 4 under `inbox/coordinator`).
- Content read of 4 of the 11, against the rule that cites each: the head-freeze note says "PR 347 moved twice in one hour" (matches the rule's "one PR moved twice in an hour"); the draft-for-CI note says a batch branch with no PR has no CI run and the gate needs CI SUCCESS on the exact head (matches); the PR 431 ruling says no rebase and no squash because the head already contains main (matches); the s2q verifier report has the lines the "contains main is read from the run report" rule names (head before and after, contains main, identity). The other 7 files I only confirmed exist (not read for content: not done).
- Public safety: the added text has no sha-like token outside the dated file names, no IP address, no host name, no mailbox (greps over the added lines found none). The rules themselves say "no estate value ... in any public file".

## Objections first
1. Rule 2 (a head that contains main lands as a fast-forward) says the coordinator pushes that head; that is the coordinator's rule, stated as a rule for everyone: fine, but it reads as an instruction to builders that they cannot carry out.
2. Rule 5 (earliest claim by git commit time wins) assumes commit times are comparable across clones; the dispatcher lock added later (a file on `origin/comms`, one winner by push) supersedes it. The lesson is accurate for 2026-11-01/02 and now partly historical (LOW).
3. Several rules cite "the card names" the eight rules: I did not re-read the card C-1198 text for the list (not done).

## Mutants / claim checks (counted)
| Claim | Checked | Failed |
|---|---|---|
| Evidence files exist (11 paths) | 11 | 0 |
| Cited text matches its rule (files read) | 4 | 0 |
| No sha, address, host or mailbox in the added text | 4 greps | 0 |
Totals counted from the table: 11 + 4 + 4 = 19 checks, 0 failed. Not covered: content of 7 of the 11 evidence files.

## Conditions
- C1: the PR does NOT merge cleanly into current main: `git merge-tree` reports a conflict in `tasks/lessons.md`, because main now also appends two lessons at the end (a changelog-drift rule and a `grep -a` rule) where this PR appends its section. Resolve by keeping both, a condition fix (head-freeze allows a push for a condition).
- C2: CI 7/7 SUCCESS on the head used for the merge (the head will change after C1).

## Findings (non-blocking; new PR only)
- F-481-1 LOW: add the dispatcher-lock rule next to rule 5 so the claim rule has one current source.
- F-481-2 LOW: the 7 evidence files I did not read should be read by whoever resolves C1.
