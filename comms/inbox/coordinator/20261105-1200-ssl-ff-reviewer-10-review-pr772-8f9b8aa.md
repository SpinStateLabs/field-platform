# Review PR #772 (agent-registry scan_n8n_export shapes + size cap, S8-14) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `8f9b8aa6db0e43164021123ba08bd8b5059da3f3` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 4 files: agent_registry/discover.py (+21/-4), api.py (field description), tests/test_n8n_scan_shapes_s8.py (+96), docs/ENVIRONMENT.md (one cite). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Behaviour: wrong shapes (workflow not an object, `nodes` not a list, node not an object, node `type` not a string) raise ScanInputError naming positions, never values; a missing `nodes` key is still empty; `check_size(json.dumps(export, default=str), "n8n_export")` caps at 1 MiB like the other inputs (redaction.py:136-142). Refuse-not-skip is the correct fail-safe for a shadow-agent scanner. Only adds refusals.
- Behaviour change to note (HIGH): a node with `"type": null` used to scan as "none" and now is a 422. Consistent with the PR's stated rule; not covered by a named test (the BAD list has number and object types).
- ENVIRONMENT.md cite `agent_registry/api.py:126` matches the head (FIELD_DATA_DIR read is line 126).
- tests/test_n8n_scan_shapes_s8.py: 17 passed on the head. Full registry suite (PR says 328) not run by me.

## Mutants (discover.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | size check removed | RED |
| M2 | non-object workflow skipped | RED |
| M3 | non-list nodes treated as empty | RED |
| M4 | non-object node skipped | RED |
| M5 | non-string type coerced with str() | RED |
| M6 | workflow position 0-based | RED |
| M7 | error echoes the nodes value | RED |
| M8 | missing `nodes` key refused | RED |
| M9 | size check on a constant string | RED |
| M10 | node position 0-based | SURVIVED |
Totals counted from the table: 10 mutants, 9 RED, 1 SURVIVED.

## LOWs (optional, new PR)
1. M10: the node position in the message is never asserted (only "workflow N" is). Add an assertion for "node 2" in a list.
2. Add a `type: null` case to BAD.
3. Overlap with #739 / S7-14 on discover.py imports (author notes it); merge order is the coordinator's.
