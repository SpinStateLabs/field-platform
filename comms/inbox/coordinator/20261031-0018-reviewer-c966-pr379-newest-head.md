VERDICT: PASS WITH CONDITIONS on a020c33dcecfea9412f1ff7fa74e774b0cfda445

Reviewer Lane 15, cloud-reviewer, C-966, PR 379 (deploy runbook). The head moved since my C-906 (2d6a167): one new commit, a020c33 (5 lines changed, runbook only). UNVERIFIED: no GX10, CI not read. Checks ran on a scratch tree of current main (acaf5f2) with this PR merged.

## Objections first
1. Main moved: the soak-time commit (five minutes) and the compose bind-source and CI guard commits of batch BZ2 are on main now. In the merged state, one-hour soaks: 0 lines; five-minute soaks: 3 (:925, :949, :1000). So my C-906 objection 1 (soak rule not met) is closed by main, not by this PR (HIGH, run).
2. C-870 C1 (the blocking condition, build ids surviving on neighbouring lines): CLOSED since 2d6a167 and still closed: of the 7 id-shaped tokens on lines this PR removes, 0 remain in the merged file (HIGH, run).
3. Deploy-status wording, the rest of my C-906 objection 2, is partly closed: a020c33 rewrites :484-485 to "23/23 is the pass state of this check (observed on both estates at deploy time; dates, builds and releases omitted)", the section 7 heading from "NOT armed on any estate" to "arming is a separate step that needs Don's approval", :1636 from "every image deployed today" to "any image from before PR #32", and :1059's date to a placeholder. The :484 sentence still states that the check was observed passing on both estates; that is a deploy observation without a date, a milder form of the same thing. MEDIUM, Don's call (HIGH read).
4. The heading change is pinned by a test that finds the section by its number: tools/tests/test_gb10_caddy_tls.py:379 and :382 look up "## 7. Phase G" (prefix), so the new heading does not break it; 237 tests that name the runbook pass in the merged state (HIGH, run).

## C-870 conditions and the card's checks
- C1 closed (objection 2). C2 (workstation name): the name remains on 2 lines on this head alone; PR 342 removes it (merge-tree clean with 342); unix home paths 20 and Windows profile paths 3 remain here, also PR 342's scope (HIGH, count). C3 soaks: closed by main. C4 (approval in chat at the start of the deploy sections): still 0 hits for "in chat"; the five "Don's go" lines are arming steps only (HIGH, grep). The new section 7 heading now names Don's approval for arming.
- Every command against the script it calls: the outside-repository scripts are tagged at every mention (my C-906; 11 names, with the correction); a020c33 touches none of them. In-repo flags were verified in C-870; not re-run.
- Scrub completeness: ISO dates 8 lines (decision and ruling dates); no estate address, flag value, build SHA, credential or e-mail added by a020c33 (sweep of the 5 changed lines: none) (HIGH).

## Evidence
Merged state with main acaf5f2: no conflict; also clean with PRs 340, 341, 342, 382. Author and committer: the no-reply Don Hagell identity on all three commits.

## Conditions
1. Decide whether the :484 sentence stays (non-blocking).
2. The approval-in-chat line and citation re-grounding docs card (carried, non-blocking).
3. Merge with PR 342 so the workstation name and profile paths go.

Not verified: CI, GX10, outside-script behaviour.
