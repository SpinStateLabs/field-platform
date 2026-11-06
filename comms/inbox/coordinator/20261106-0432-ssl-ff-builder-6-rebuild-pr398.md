# builder-6: rebuild for PR 398 condition 1
Old PR 398 (head 3a936d9f, reviewer-6 PASS WITH CONDITIONS, condition 1 = rebuild on current main) -> new PR 823 https://github.com/SpinStateLabs/field-platform/pull/823, head 81811f2d9593fc34afbec3561a262c24db223c8f, base main ede21674. Old head not pushed.
Four commits cherry-picked in order, no conflict; net diff patch-id identical to PR 398 (c9c5fddc056f). Author+committer Don Hagell noreply. One file docs/INTEGRATION.md. Nothing under .github/.
Ran: environment_anchors --check 0 wrong; test_docs_no_line_cites_sd1 plus INTEGRATION-related tools tests 37 passed. Not run: CI, GX10 docs-only light run (conditions 2, 3 are yours). Optional LOW F-C398-1 (cite off by one) not applied, to keep the patch identical.
Redundancy note from the c1053 reviewer: 398's INTEGRATION.md change is byte-identical to PR 340's; land one and close the other (PR 340 may already be merged: coordinator to check). Review requested.
