# Report: S-C3 (scout round 3), builder. UNVERIFIED (cloud, no GX10). Contains an OPEN QUESTION FOR DON.
Claim check: no branch or note for fleet-halt registry shapes.
PR 523 (draft): https://github.com/SpinStateLabs/field-platform/pull/523, branch fix/fleet-halt-registry-shape-sc3, head 9f867f4065095a1d8ededf5f313eeb6a6436cd94 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane B: ops-console).
Bug (R, 9 red tests): POST /api/fleet/halt with no explicit domains: a registry answer that is a dict, string, number or a list of non-objects, or an agent with a non-string domain, raised inside the domain enumeration: a 500 at the moment an operator is halting the fleet. Fix: such an answer is a 502 with fixed text BEFORE any kill-switch call, nothing echoed. Well-formed fleets and explicit domains unchanged.
OPEN QUESTION FOR DON (not decided, pinned by a test that says so): an EMPTY non-retired fleet answers 200 all_ok:true domains:[] results:[]: "nothing to halt" reads as success, and an operator in an incident may read all_ok:true as "the fleet is halted". Options: keep, all_ok:false, or a 4xx. I did not read how the UI renders all_ok.
13 tests; ops-console 470 passed; boundary-echo/env-doc/anchors/frame-header tools tests 170 passed; anchors --check 0 wrong; one mutant 9 red.
Not run: other suites.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511, 512, 513, 514, 517, 518, 519, 521, 522, 523; none merged by me.
Round 3 not yet taken: S-C2, C8; docs/CI S-D1..D8.
Decisions waiting on you or Don (collected): /halt 200 vs 502 (S-B4, PR 514); empty fleet halt all_ok (S-C3, PR 523); slug length cap (S-B7 note); crosswalk agent_id pattern (S-B5 note); domain case-folding (S-B6 note); federation `_lists_org` substring match (S-C notes).
