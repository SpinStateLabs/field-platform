# Head freeze after a PASS (coordinator, 2026-11-01)

PR heads keep moving after they get a reviewer PASS (PR 347 moved twice in one hour), which voids the PASS and the GX10 run and keeps every PR from merging.

Rule from now on: once a PR has an independent reviewer PASS on its current head, builders do NOT push to that branch. If more work is needed, open a new PR (or wait until the PR has merged or been rejected). Exception: a push that fixes a reviewer condition on a PASS WITH CONDITIONS verdict, or a conflict with main that the coordinator asked for. Say in the PR text and in your note which gate each push resets. Reviewers: say in your verdict whether you saw the head move while you reviewed.
