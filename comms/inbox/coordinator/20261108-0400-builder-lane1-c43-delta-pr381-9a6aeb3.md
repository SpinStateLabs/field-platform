FROM: builder Lane 1 (cloud). RE: C-43 delta on PR 381 8c781bb (item 6).

PR 381 new head 9a6aeb3304530a47e2626e31fe56c63514961983 (one test-only commit on 8c781bb; no force-push; Don Hagell author and committer; trailers). Needs its own review: the C-43 PASS names 8c781bb.

Survivor killed: new test in services/lifecycle-manager/tests/test_lifecycle_headers_r3.py: a lifecycle CLI GuardedOperatorAuth built with pair=None sends POST /kill/a1 with no x-field-operator or x-field-operator-key, does not raise, and the client's x-field-auth header is still sent. Mutant (the "is a pair configured" check dropped from the CLI guard copy) red, 1 failed. No source change.

Tests, EXIT=0 each, at 9a6aeb3: lifecycle-manager 263 passed; whole tools via /workspace/resumable-suite.sh (venv-ci, PYTHONPATH of the worktree's src dirs, new state dir), files ok 53 of 53. Not re-run: field-core, kill-switch (untouched since f083ed2), sealed-ledger, agent-registry, delegation-authority; GX10 and CI not run. PR body updated.
Blockers: none.
