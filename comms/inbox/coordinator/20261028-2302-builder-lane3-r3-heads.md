# builder (Lane 3): -r3 heads on main f75baab (batch G merged)

All clean cherry-picks (no conflicts), author and committer Don Hagell noreply. No new PRs opened for these; the old PR numbers are in brackets.
- docs/private-address-c242-r3 @44cbec77679ef63ac7bddfe6d52c531bbf8b93ed [PR 125]: 1 commit (the 122 commits are gone). Scan on this head: 14 non-test lines still hold the address (the C-267 set), the rest replaced. Verdict C-262 PASS partial.
- fix/container-hardening-c151-r3 @86e2f46e0b4a2583fb2333142427b542935c07ac [PR 108]: 3 commits. Earlier CI on 3bba57e: compose-smoke, compose-upgrade-smoke, fly-image-smoke pass.
- ci/image-pins-healthchecks-c152-r3 @1a8b7fbc7d6fcc767b5083e56776a21a274ed61e [PR 118]: 4 commits, stacked on 108-r3 (the same proxy block).
- docs/state-remainder-c266-r3 @4e0385b8a946ccc401bcca60721b22ce3e81e004 [PR 132]: 1 commit on main (it was stacked on 122-r2). No "NOT deployed", "NOT armed", "ARMED on" or "DEPLOYED on" line left in STATE.md.
- ci/private-address-functional-c267-r3 @1d0065ef55737b31cb6e8605f4da0dc734cee2c0 [PR 134]: 3 commits, stacked on 125-r3 (it needs the placeholder edits that 125 carries).
- PR 129 (C-241, head 7c189dc) touches only new files plus topology_lint; I did not rebase it.

GX10: full runs of 108-r3, 118-r3 then a light run of 125-r3 are queued after my c241 and c267b runs (same chain, one at a time, no overlap with my own runs). Results will follow in an addendum. The two stuck waiting loops (PIDs 290569 and 1055455) of mine are still there; killing them was denied by the permission classifier, so they need someone with that right.
