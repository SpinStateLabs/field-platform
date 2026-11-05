# Builder Lane N: PRs 538 and 553 merged on Don's authority; all five of my PRs are now on main
- PR 538 -> 078967e4 (head b8867f70, 7/7 checks green, mergeable clean). PR 553 -> 3cede872 (head ba7f250d, 7/7 checks green, mergeable clean). Squash, pinned to the head SHA. Earlier: 537 -> 06526f12, 540 -> 37c6d729, 534 -> ebb027a2.
- 553's CI ran on a base before 538 merged; I tested the combined tree locally before merging (environment_anchors --check 0 wrong; test_docs_no_line_cites_sd1 + environment doc/anchors tests 100 passed; agent-registry 314 passed). main's own CI on 3cede872 is NOT yet observed by me.
- Please re-run environment_anchors --check on main 3cede872 and look at main's CI: five merges moved anchored lines in docs/ENVIRONMENT.md and ARCHITECTURE.md.
- None of the five had an independent review; no GX10 run. Open decisions from the PR bodies: registry fail-closed vs count (553); the S-C8 CLI is still blocked on PR 462 (C-1179).
