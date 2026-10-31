VERDICT: PASS WITH CONDITIONS on 2ab0e8a666ac64e98310ee5ceb400a0c53d3a42a

Reviewer Lane 15, cloud-reviewer, C-961, PR 325. The card names head 5955870; the PR head is now 2ab0e8a (one new commit, builder C-837, which answers my C-879 and Lane 4's C-837). UNVERIFIED: no GX10, CI not read; scratch tree.

## Objections first
1. A search of this repository cannot prove a name has no reader: callers in other repositories (plugin repos, estate scripts) are invisible to it (the same limit as my C-879). PASS is for this tree (HIGH).
2. One string occurrence needs naming so nobody mistakes it for a reader: services/delegation-authority/src/delegation_authority/clients.py:15 holds the quoted name AgentNotRegisteredError. That module re-exports it from field_core.clients for delegation-authority; the PR removes the unused import from compliance-crosswalk's api.py only, and nothing imports the name from there (word grep of services/compliance-crosswalk: 0 hits) (HIGH, run).
3. The removal date 2027-01-31 on the two deprecated helpers is the builder's proposal, not a ruling; the docstrings now say "proposed, not yet a ruling". The test enforces only a valid calendar date and a fixed floor of 2026-11-01; nothing fails or warns when the date passes (HIGH, read). A card to port the roughly 25 test assertions and delete both helpers is still unopened (builder note C-837).

## Every removed name has no reader (whole tracked tree, all file types, word match)
- MAX_OPERATOR_LEN and MAX_KEY_LEN (operator_auth.py): 0 hits anywhere; the live caps are the regex literals at operator_auth.py:84 (`{1,64}`) and :85 (`{1,256}`), pinned both sides.
- AgentMap (claude_approver/core.py import): 0 hits outside claude_approver/config.py, where it is defined and used (9 uses); core.py's syntax tree does not use it.
- AgentNotRegisteredError (compliance_crosswalk/api.py import): see objection 2; api.py's syntax tree does not use it.
- `re` import in field_core/validation.py: the module's syntax tree has no use of `re` (the operator_auth.py module keeps its own).
- String lookups: quoted forms of the four names: one hit, objection 2. No __all__ in the four edited modules; no star-import of them anywhere (HIGH, run).

## C-837 / C-879 conditions at this head
- F-C837-1 (removal date unparsed, mutants D4 and D5 survived): CLOSED as stated by the builder: the test parses the date and floors it. Mutants on both helpers: a past date (2020-01-31) and an impossible date (2027-13-45) each fail the test, on the first and on the second helper (4 of 4 killed) (HIGH, run). Remaining: the floor is fixed, not "today"; nothing enforces the date after it passes (objection 3).
- F-C837-2 (passkey label cap unpinned): CLOSED. New test `test_the_passkey_label_cap_is_exactly_64`: 63 and 65 variants of the pattern at operator_auth.py:234 both fail; the operator id cap (:84) and key cap (:85) mutants at 63/65 and 255/257 all fail (6 of 6 killed) (HIGH, run).
- F-C837-3 (the keep decision keeps dead code): partly: docstrings say only tests call the helpers and to port them; the follow-up deletion card is unopened (OPEN, coordinator).

## Evidence
field-core 1123 passed, 1 skipped; claude-approver 282; compliance-crosswalk 353 passed, 5 skipped (HIGH, run). Overlap: PR 325 edits operator_auth.py, validation.py and two service files; merge-tree with main and with PRs 349, 351, 355, 369, 374, 375, 381, 383, 388: no conflicts (HIGH, run; 375 and 383 also edit operator_auth.py, different hunks). Author and committer: the no-reply Don Hagell identity on all four commits. Files restored; worktree removed.

## Conditions
1. Open the card to remove the two deprecated helpers (coordinator). Non-blocking.
2. Ruling (or a rejection) of the 2027-01-31 date; consider a test that goes red on the date. Non-blocking.

Not verified: CI, GX10, callers outside this repository.
