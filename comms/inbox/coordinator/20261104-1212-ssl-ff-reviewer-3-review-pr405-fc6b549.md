# Review PR 405 @ fc6b5492c4e3ac64277791346c918dc8e4417673 (C-504 / C-1068: registry or state failure reaches the caller as a class name) - reviewer ssl-ff-reviewer-3

**VERDICT: BLOCK on head fc6b5492 as a branch (lineage). The patch itself passes on a clean rebuild. UNVERIFIED (cloud, no GX10).**

## Blocking finding (HIGH, measured)
- F-R405-1 BLOCK: no merge base with current origin/main (97dcfec1; `git merge-base` fails); `git log origin/main..pr405` lists 427 commits (old pre-rewrite history, same condition as PRs 408, 419, 420). It cannot fast-forward; a merge would import 427 commits, many with non-noreply identities (see the PR 420 report for the measurement; this head shares that history).
- The PR's own work is 2 commits above acaf5f24: f101fe78 and fc6b5492, both Don Hagell noreply for author AND committer (measured).

## The patch, measured on a clean rebuild (main 97dcfec1 + `git cherry-pick acaf5f24..pr405`, scratch only)
- Applies with no conflict (one auto-merge in kill-switch api.py). 4 files, +263 -9: kill-switch `api.py` (`_exc_name`, `_STATUS_ONLY`, `_registry_reason`, 8 reply/ledger sites), lifecycle-manager `api.py` (1 line), and 2 test files.
- Baselines unmutated: kill-switch full suite 282 passed; lifecycle-manager full suite 271 passed; the two new test files 12 passed and 2 passed. Relative PYTHONPATH including the sibling service `src` dirs (the lifecycle suite needs spend_governor, delegation_authority and conformance_sentinel on the path). One early mutant run had a collection error in the lifecycle baseline (missing path); I discarded it and re-ran: the table below is the re-run, baseline 0 for both.
- Boundary-echo lint (C-505) with 405 applied on main: 61 passed. The 6 `pending-405` allowlist entries in main's `boundary_echo_allowlist.txt` do not turn the lint red; whether those entries should now be removed is the owner's call (not in source).

## Mutants (the two new test files; files restored, worktree clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| `_exc_name` is the cause's class name, never text (N1-N4) | 4 | 4 | 0 |
| `_registry_reason`: cause by class; uncaused text only in the status-only shape (Q1-Q4) | 4 | 4 | 0 |
| status-only regex is a full match of "registry returned NNN" (Q5-Q8) | 4 | 4 | 0 |
| every kill-switch reply and ledger site (kill x2, kill_domain, revive x2, liveness, signal error x2 shapes, drill restore) (S1-S9) | 9 | 9 | 0 |
| lifecycle `state unreadable` names the class only (L1-L4) | 4 | 4 | 0 |
Totals counted from the table: 4+4+4+9+4 = 25 rows; killed 25; survived 0; anchor failures 0.

## Findings
- F-R405-2 LOW: the surviving reply still includes the class name of the underlying error (`ConnectionError`, `OSError`), which tells a caller the failure kind; this is the stated design.
- F-R405-3 LOW (not in source): whether `pending-405` allowlist lines should be deleted on landing, as that would be the lint's "list only shrinks" intent; left to the owner.

## Recommendation (coordinator's call)
Release PR 405; rebuild by `git cherry-pick f101fe78 fc6b5492` on current main as a new draft PR (clean today); fresh independent review on that head (this result carries over only for an identical patch).

## Objection
Approving the old head would approve an unmergeable branch; the 25/25 covers the rebuilt patch only.
