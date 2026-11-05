# Review PR #689 (S5-13 sentinel /check bounds + registry-id shape check) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `c6e51221a854f8db003402eb72bc00336b71374d` (merge-base b963407a; PR is draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 2 commits (7c927109, c6e51221), 2 files: conformance_sentinel/engine.py (+38/-4), tests/test_check_request_bounds.py (+126). Nothing under .github/. Both commits author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Only adds refusals: max_length on agent_id/token_id (200) and action (2000); context <=50 keys and <=16384 UTF-8 bytes via field_validator (non-JSON/recursion mapped to ValueError => 422); agent_id outside `[a-z0-9][a-z0-9._-]*` (fullmatch) answered BLOCK R.unregistered with no registry call, after the ledger-unreachable check. The regex equals the registry's own pattern (agent_registry/models.py:22, `^...$`) (HIGH). fullmatch rejects a trailing newline (tested "a\n").
- Sentinel tests/test_check_request_bounds.py: 25 passed on the head (3m40s, with all service src on PYTHONPATH, run in services/conformance-sentinel). The full sentinel suite (PR claims 288) was not completed by me: my one attempt overlapped the mutant runs on the same worktree, so I discount it (not verified).

## Mutants (engine.py, one at a time, file restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | agent_id max +1 | RED |
| M2 | action max +1 | RED |
| M3 | token_id max +1 | RED |
| M4 | keys check `>` to `>=` | RED |
| M5 | bytes check `>` to `>=` | SURVIVED |
| M6 | size counts characters not bytes | RED |
| M7 | fullmatch to match | RED |
| M8 | regex admits uppercase first char | RED |
| M9 | regex admits `/` | RED |
| M10 | shape check skipped | RED |
| M11 | RecursionError not caught in validator | SURVIVED |
| M12 | TypeError not caught in validator | SURVIVED |
| M13 | ensure_ascii True (escaped size) | RED |
Totals counted from the table: 13 mutants, 10 RED, 3 SURVIVED.

## Survivors (all LOW, none blocks)
1. M5: the exact 16384-byte boundary is not tested (the test uses MAX-20 accepted and MAX+len(MARK) rejected). Add a context of exactly 16384 bytes (accepted) and 16385 (rejected).
2. M11/M12: the deep-nesting test accepts 200/400/422, and the body parser refuses depth first on this stack, so the validator's except branches are not reachable through HTTP here; a direct `CheckRequest(...)` unit test of a self-referential or non-JSON-able dict would pin them.
3. Reason text echoes the (<=200 char) submitted agent_id for a malformed id; the same text the existing unregistered path already returns (engine.py:516, :523), so no new echo class (HIGH). Control chars in that id land in the ledger payload; not new.

## Policy note
The author asks Don to decide BLOCK R.unregistered vs 422 for malformed ids; not a review item. Not checked: any live caller using ids outside the registry pattern (author says unchecked too).
