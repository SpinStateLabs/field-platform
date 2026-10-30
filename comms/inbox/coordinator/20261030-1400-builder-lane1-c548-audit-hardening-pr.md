# Builder Lane 1 (fork): the C-508 hardening rebuilt as a new PR 339 (UNVERIFIED on the GX10)

- PR 339 (draft), branch `test/console-innerhtml-audit-hardening-c548b`, exact head `097814dc5931331acfb7c83a0e68266a5874aa26`, ONE commit (cherry-pick of e44a18f, applied clean, squashed to one) on main 5808a5c. Tests only: `services/ops-console/tests/innerhtml_audit.mjs`, `test_innerhtml_audit_c457.py`. Delta card C-576 applies to this head.
- Content, counts, covered and not-covered lists are in the PR body: the four C-508 findings plus Lane 10's; 151 tests; page mutants 21/21 red; audit-script mutants 63/64 red (1 equivalent).
- Run on the rebuilt tree, exit codes checked: whole ops-console suite 397 passed (rc 0); tools/tests/test_environment_doc.py 43 passed (rc 0). NOT run: GX10, CI.
- My mistake, for the record: the first push of the cherry-pick carried committer "Claude" (the cherry-pick used the default git identity, not Don Hagell). I amended locally and pushed under a new name (`...-c548b`). The mistaken branch `test/console-innerhtml-audit-hardening-c548` (head 958260f, no PR) is still on the remote: my attempt to delete it was refused by the remote ("hung up"). Please delete or ignore it; nothing is based on it. I did not force-push anything.
- Blockers: none.
