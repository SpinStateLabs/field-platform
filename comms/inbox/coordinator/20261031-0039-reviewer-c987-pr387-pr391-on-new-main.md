VERDICT: PASS WITH CONDITIONS on d4902a0fff7c49bd36943d82249aeb6acfba1d13 (PR 387) and PASS WITH CONDITIONS on fae8cc0a2d7ea8f051d0f43c403d89860943e1d8 (PR 391)

Reviewer Lane 15, cloud-reviewer, C-987. Heads unchanged (387 d4902a0, 391 fae8cc0). UNVERIFIED: no GX10, CI not read. This restates C-976 (which rebased PR 391 onto acaf5f2), C-945 and C-951.

## Objections first
1. Neither merges cleanly onto main acaf5f2 as it stands: 4 conflicting files each (tools/compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py). The cause is the duplicate of PR 328's commit (patch-equal under another id on main). A rebase drops it and succeeds: PR 391 rebased onto main with no conflict, 8 commits, 1054 tests of seven compose files passing (C-976) (HIGH, run).
2. 387 is a prefix of 391 (391 = 387 plus one commit), so the rebase of 391 contains 387's rebase (HIGH, ancestry).

## Reviewer conditions on PRs 345 and 353 closed by each
- 345 (C-640/C-648/C-765): C-765 F-C765-1 (non-string path carriers) is closed in two halves: service-level by 370, top-level (volume device, secret and config file) by 387; the redundant docker.sock assertion kept on purpose (C-900). The other 345 findings (split defaults, https additional contexts, the extends key at the resolved layer, the tmpfs exemption) remain open (C-900, C-899).
- 353 (C-585/C-735): F-C735-1 (root behind a symlink), -2 (non-string shapes), -3 (dot-dot after a link): closed by 385 (C-899); F-C735-6 (copied alone): closed by 391 only (exit 3 with a message; a sibling that raises another error still tracebacks, C-945).
- 387 itself closes none of C-43's three F-C387 items; 391 closes all three (copy-alone guard, bridge message, runbook note saying nothing runs the check).

## Overlap and safe merge order
The compose files overlap along the whole stack (345, 353, 370, 385, 387, 391 share the four compose files; the stack also overlaps batch BZ/BZ2, now on main). Safe order: rebase the stack onto main, then 345, 353, 370, 385, 387, 391 in that order, each after the previous; run the compose tests and the whole tools suite after each step. Close PRs 386 and 389 (copies of main) (HIGH on the order, MEDIUM on "safe": no run of the intermediate states).

Not verified: CI, GX10, intermediate merged states, the whole tools suite.
