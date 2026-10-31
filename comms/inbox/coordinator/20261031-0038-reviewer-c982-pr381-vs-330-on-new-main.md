VERDICT: PASS WITH CONDITIONS on f083ed2ca2faeddd8575a2be37bcb44ead9a45a8

Reviewer Lane 15, cloud-reviewer, C-982, PR 381 at f083ed2 (unchanged since my C-950). UNVERIFIED: no GX10, CI not read. Evidence is in my C-950 report; this one answers the card's three questions on main acaf5f2.

## Objections first
1. Premise check: the card says PR 330 f0e9e70 had C-838 PASS WITH CONDITIONS; its three conditions map as below. PR 381 is the head that replaces both 318 and 330; the verdict is on 381 only (HIGH).
2. The trust_env limit is carried, not fixed: LedgerClient, RegistryClient and the two CLI clients still read the process proxy environment while carrying the perimeter secret and, on a guarded write, the operator pair; the PR states it (module docstring) and leaves it to C-487 (HIGH, C-950).

## C-838 conditions at the 381 head
- (a) merge procedure for 330 (with 318): not needed for 381; it is one branch on main, so the two-path merge dance is gone. 381 merges clean against main acaf5f2: 0 conflicts (merge-tree, re-run now) (HIGH).
- (b) carried trust_env limit (F-C838-1, proven by a live proxy listener): OPEN, declared (objection 2).
- (c) followed redirect not covered by the origin check (F-C838-3): CLOSED for the clients that carry the pair: kill-switch CLI client built with follow_redirects=False (kill_switch/cli.py:152) and the lifecycle client forces it on every call path (lifecycle_manager/api.py:122, :134); mutants removing either fail tests; the module docstring states that GuardedOperatorAuth alone does not stop a followed redirect (HIGH, C-950).
- C-731 wire-path conditions and C-792 merge trap: closed (C-950 probe of 21 spellings; one PerRequestAuthClient definition).

## Merges clean on main acaf5f2? Can 318 and 330 close?
- PR 381 vs main: 0 conflicts. PR 318 (4383a07) vs main: 0 conflicts (still a clean, now redundant copy). PR 330 (f0e9e70) vs main: 1 conflict (it has aged against main).
- Nothing of either old PR is dropped by 381 (C-950: 0 lines and 0 tests lost apart from lines 381 deliberately replaces: the old constructor signature, two stale docstring lines, three ENVIRONMENT.md cells, one extended test decorator). So 318 and 330 can close once 381 merges; merging 381 and leaving them open guarantees conflicts (HIGH).

## Conditions
1. Merge 381; close 318 and 330 together. 2. Track F-C877-1 (proxy environment) as C-487. 3. GX10 merged-state run (not done by me).

Not verified: CI, GX10.
