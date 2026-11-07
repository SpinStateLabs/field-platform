# Delta review PR 689 (S5-13 sentinel /check bounds + registry-id shape check) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS** on head `1dfb10130cfc2fff0dd052fe39f05328f98539d6` (draft, base main). It is reviewer-10's passed head c6e51221 plus a merge of main ccd013d4 (current origin/main); the only conflict was one import block. Standing gate: CI and GX10 on this head (GX10 verifier-6 ran at c6e51221, not here). Optional LOWs go in a NEW PR.

Independence: I did not build or fix this PR (3 commits, none mine; the merge is builder-8's per its note).

## Checks (HIGH, run by me)
- Identity: 3 of 3 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Shape: second parent of the head is current origin/main ccd013d4f (not behind); `git merge-tree` against origin/main is clean. Diff vs main: 2 files, engine.py +42/-4 (reviewer-10 counted +38/-4 at c6e51221) and tests/test_check_request_bounds.py +126.
- Merged import block (engine.py:14-21): `json`, `logging`, `re` all present, `field_validator` imported; main's `logging` and the PR's `json` and `re` kept, as the builder says. Source delta vs the passed head is those import lines only.
- Tests on the exact head (Windows, py3.14, from services/conformance-sentinel, all service src on the path): `test_check_request_bounds.py` 25 passed (495 s, the box is loaded). I did not run the full sentinel suite.

## Mutants (6 on the PR's claims, one at a time, file restored and tree verified clean; counted from the table)
| # | mutant (engine.py) | result |
|---|---|---|
| M1 | AGENT_ID_MAX 200 -> 201 | KILLED |
| M2 | context keys check `>` -> `>=` | KILLED |
| M3 | `fullmatch` -> `match` on the registry-id pattern | KILLED |
| M4 | the id shape check skipped (`if False`) | KILLED |
| M5 | context size counts characters, not UTF-8 bytes | KILLED |
| M6 | context bytes check `>` -> `>=` | SURVIVED (25 passed) |
Totals: 6 attempted, 5 killed, 1 survived, 0 not applied.
M6 is reviewer-10's survivor M5 carried forward: the exact 16384-byte boundary is not tested. Not a defect of the change, a test gap (LOW); fix with one context of exactly 16384 bytes (accepted) and one of 16385 (rejected).

## Carried forward (not re-opened)
Reviewer-10's survivors M11/M12 (RecursionError/TypeError branches in the validator are not reachable through HTTP here; a direct `CheckRequest(...)` unit test would pin them) and the policy question for Don (BLOCK R.unregistered vs 422 for a malformed id) stand.

## Heads-up
PR 606 (open) edits the same engine.py (builder-8's note); whichever lands second needs a rebase.

## Not verified
CI; GX10; Linux; the full sentinel suite on this head; any live caller sending an id outside the registry pattern.
