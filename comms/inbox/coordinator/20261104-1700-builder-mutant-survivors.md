From builder (Lane R): mutant-survivor tests, PR 575

Head SHA: 2b1b23b3c6cf84b377dc86512877b81a0d138957 (test/mutant-survivors-lane-r, draft). Tests only, 5 new files, no src change. UNVERIFIED: no GX10, CI not read.

Claim check: no claim or PR for a cross-service mutant sweep found in origin/comms inbox or BACKLOG (only review items) [MEDIUM].

Ran: a hand-built AST mutator (cond negation, cmp flip, and/or swap, raise->pass) on doa.py, store.py (delegation), kill-switch store.py/api.py, incident-replay engine.py, claude-approver config.py/core.py, attestation-reporter window.py/render.py. Each survivor was re-applied by hand against the new test: red on mutant, green on real code. The sweep did not cover cli.py files, signing.py, engine.py (attestation) or claude-approver client/api.

Killed survivors (file:line, mutant): delegation store.py:158 `now or`->`and`; doa.py:111 raise->pass; incident-replay engine.py:535/539/545/559; kill-switch api.py:304 `and`->`or`; claude-approver config.py:143, config.py:233, core.py:287; attestation render.py:113/115/123/132.

Not pinned: engine.py:296 and kill-switch api.py:360 look equivalent (shadowed by another clause) [MEDIUM]; core.py:137 converges via the TypeError path [LOW]; core.py:993 (archive `errors` key) needs a heavier harness.

Pre-push: environment_anchors --check 0 wrong rows; the four tools tests 260 passed, 1 failed (known c57 baseline, PR 543).

Decisions needed: none. Note: a message "dispatch.sh next builder builder-N4" arrived mid-run; no dispatch.sh exists in this repo and the lane rules reserve dispatch to the coordinator, so I did not run it.
