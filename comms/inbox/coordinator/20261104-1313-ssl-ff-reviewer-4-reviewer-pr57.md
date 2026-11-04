# Reviewer report: PR 57 @ 30ac1e11c259656259148e230fbde5ae6facc6c1 (key rotation R4a, rotator core)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base ad424103; 14 commits incl. 2 merges of main; 10 files (+4749/-2): field-core rotation.py (+1693), rotation_events.py, tools/operator_rotate.py (+259), and 6 test files. The PR is held for Don (per earlier notes); this review covers the exact head and does not replace Don's decision. `git merge-tree --write-tree origin/main pr57` is clean (HIGH). Trailers: 6 Opus 5.5, 5 Sonnet 5.5, none Fable.

## Objections first (one is blocking as it stands)
1. IDENTITY (HIGH, run by me, public repository): six commits, 74ca7398, 7a8b1112, 817968e2, 5ab1dc80, 306c50a5 and 09dcbcd0, have an author NAME that is an email address, an EMPTY author email and an EMPTY committer email, and a committer name that is not the repository identity. (Fields by class only: I do not copy the value into this note, as the repository's own identity guard asks.) The other 8 commits are Don Hagell 13129187+dhagell@users.noreply.github.com. This is a personal mailbox sitting in public PR history; the PR 346 guard would flag all six on the author name and both emails. Per the coordinator's PR 381 ruling a commit may be re-authored INSIDE a batch branch only (cherry-pick --reset-author, patch-id identical); the PR head itself must not be pushed to.
2. The rotator writes the file that decides who may act on the estate (operators.json) and keeps two keys alive across a soak; every phase after PROMOTE is a half-state. A rotator core is only as safe as the weakest unpinned branch, and the mutants below show which branches are unpinned.
3. Prior reviews (C-18, C-496 delta, C-605, GX10 verifier A on this exact head: 8243 passed, 0 failed, per its note, not re-run by me) already carry open findings F-C18-2 (lost update), -3 (foreign-edit freeze), -4 (self identity aborts on resume), -5/-6/-7; I did not re-probe them and they stay open unless the builder or coordinator rules otherwise.
4. 1693 lines in one module with a state machine, journal, lock, diff guard, auto-revert, 9b and migration: I sampled the behaviours listed below, not every line.

## Verified (run by me)
- Baselines on the exact head (relative PYTHONPATH `packages/field-core/src:tools`): the six R4a test files 207 passed; with test_rotation_events_r2.py and tools/tests/test_deployment_agent_rotation.py 671 passed.
- The proxy blocker of C-496 is fixed on this head: tools/operator_rotate.py builds its client with `trust_env=False` (read; same conclusion as C-605, not independently probed).

## Mutants (mutations of rotation.py; scratch worktree on the head; kill = at least one failure in the six R4a files, `-x`)
| # | Mutant | Result | Killed |
|---|---|---|---|
| D1 | generation may stay equal | 1 failed | yes |
| D2 | generation type unchecked | 1 failed | yes |
| D3 | rows may be added or removed | 1 failed | yes |
| D4 | break-glass row may be a target | 1 failed | yes |
| D5 | row-order check removed | 207 passed | NO |
| D6 | any field of a target row may change | 1 failed | yes |
| D7 | top-level fields may change | 1 failed | yes |
| D8 | missing target row tolerated | 1 failed | yes |
| D9 | migration with targets allowed | 1 failed | yes |
| D10 | format 1 live file accepted without migration | 1 failed | yes |
| D11 | candidate `format` type not required to be int | 207 passed | NO |
| D12 | migration may add any row field | 1 failed | yes |
| W1 | operators temp file chmod fixed 0644 (kept mode ignored) | 207 passed | NO |
| W2 | new key file mode 0600 -> 0644 | 1 failed | yes |
| W3 | new key file not exclusive | 1 failed | yes |
| W4 | private write 0600 -> 0666 | 1 failed | yes |
| L1 | lock blocking (LOCK_NB dropped) | HANG: the run was killed by my 40 s timeout, exit 124 (my first harness mislabelled this as a survivor; I re-ran it by hand) | yes (hang) |
| L2 | lock shared | 1 failed | yes |
| L3 | lock-held error swallowed | 1 failed | yes |
| P1 | retry cap 10 -> 1000 | 207 passed (a 34 s run) | NO |
| P2 | retry cap 10 -> 1 | 1 failed | yes |
| P3 | `halted` flag not in the summary | 1 failed | yes |
| P4 | `halted` status not saved | 1 failed | yes |
| P5a | failure counter not incremented in _promote | 207 passed | NO |
| P5b | counter not incremented in _fail_kept | 207 passed | NO |
| P5c | counter not incremented in _verify_current | 1 failed | yes |
| P6 | a failed promote goes back to soak | 1 failed | yes |
| P7 | retired event not removed before the retry | 207 passed | NO |
| V1 | auto-revert at the old generation | 1 failed | yes |
| V2 | post-revert "seen by every service" check removed | 207 passed | NO |
| V3 | revert event always says reverted True | 207 passed | NO |
| V4 | PolicyRefused not caught during auto-revert | 207 passed | NO |
| K1 | rotate-every 30 d -> 300 d | 1 failed | yes |
| K2 | key lifetime 75 d -> 750 d | 207 passed | NO |
| K3 | soak ticks 3 -> 1 | 1 failed | yes |
| K4 | min soak 15 min -> 0 | 1 failed | yes |
| K5 | in-flight limit 24 h -> 240 h | 1 failed | yes |
| K6 | estate spacing 6 h -> 0 | 1 failed | yes |
| K7 | jitter span 7 d -> 1 s | 1 failed | yes |
| K8 | not-before skew 5 min -> 0 | 207 passed | NO |
Totals counted from the table: 40 valid mutants, 28 killed (incl. L1 by hang), 12 survived (D5, D11, W1, P1, P5a, P5b, P7, V2, V3, V4, K2, K8). The 12 survivors run against the wider set (the six files plus test_rotation_events_r2.py, test_operator_keygen_f4_r4a.py and test_deployment_agent_rotation.py, 671 passed): all 12 still survive. My first pass also built P5-P7 with patterns that did not apply; I rebuilt them by line number (the table shows the rebuilt results). I did not run the whole field-core suite per survivor; no other file imports the rotation module (grep), so the eight files are all the tests that touch it.
Reading of the survivors: D5 is probably equivalent (a swapped row also fails the per-field loop on `operator_id`, so only the message changes); W1 is probably masked by the fixtures using the default 0644 (a 0640 live file would show it); the rest are real gaps.

## Findings
- F-R4a-1 PROCESS, blocking merge as-is: the six commits with a personal mailbox in the author and an empty committer email (objection 1). Coordinator action: re-author inside a batch only; consider who must be told that the value is already in the public PR history.
- F-R4a-2 MEDIUM-LOW: V3, the `keyrotation.failed` event payload can say `reverted: true` while the revert did not happen (mutant leaves every test green); the ledger would then record a revert that was not made. Pin both outcomes of the revert in the event.
- F-R4a-3 MEDIUM-LOW: P5a and P5b (with the prior note F-PR57D-3): the post-PROMOTE retry cap is counted on three paths and only the `_verify_current` path is pinned; P1 shows the number 10 itself is unpinned (1000 passes). Add one test per path and one for the constant.
- F-R4a-4 LOW: V2, V4 (auto-revert edge paths), P7 (retired-event bookkeeping before a retry), K2 (75-day key lifetime), K8 (5-minute not-before skew), D11 (candidate `format` must be an int), W1 (kept file mode): unpinned.
- F-R4a-5 note: open findings of C-18 (F-C18-2..-7) and the C-496 follow-ups are unchanged by this review.

## Verdict: PASS WITH CONDITIONS on 30ac1e11c259656259148e230fbde5ae6facc6c1 (code PASS; merge blocked on F-R4a-1)
Conditions: (1) the six commits re-authored inside a batch only (patch-id identical), with the coordinator deciding what to do about the value already public; (2) Don's decision to land the rotator (the PR is held); (3) F-R4a-2 and F-R4a-3 fixed on the PR (a condition fix is the only push allowed) or ruled follow-ups in writing; (4) CI green and the full GX10 run on the exact head rebased on current main (the verifier A run on this head is not a substitute after a rebase). Not run by me: CI, GX10, any estate, any key file.
