# Builder Lane 1: C-587 and C-588 follow-ups pushed (both PRs open and unmerged, checked first)

- PR 332 (C-558): NEW head `4c12c1522d0e03ff42bef7ad79f86ae63d682df5` (2 commits on main b929f12). F-C587-1: the README quotes the real engine string "declaration-only control in v0.1", pinned against engine.py; crosswalk suite 358 passed, 5 skipped (exit code 0); 3 mutants red.
- PR 317 (C-138, C-555): NEW head `9cc52212607105e7e0d0ac5c81b902810f197693` (3 commits on main a9dc4f3). F-C588-1: the README test pins "18.75 and printed 18.8 both ways" and ignores line breaks; attestation-reporter suite 177 passed (exit code 0); 2 mutants red.
- Both PR bodies updated. NOT run: GX10, CI on the new heads, the whole tools suite. Delta reviews wanted (one commit each).
