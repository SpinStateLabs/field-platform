# Review PR #777 (attestation-reporter: list/object agent_id no longer 500s the pack, S8-19) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `9f7c42a8f943b1bfd171e0f9118c35fbb6cd7a29` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 2 files: attestation_reporter/engine.py (+5/-2), tests/test_unhashable_agent_id_s8.py (+96). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Fix: `_without_canaries` treats a row as a canary only when `agent_id` is a `str` in CANARY_AGENTS; the distinct-agents key maps a non-string `agent_id` to None (falls into the existing "without agent_id not counted" note). Conservative: an odd-id row is neither dropped as a canary nor silently counted as an agent. Only adds tolerance on an error path; no verdict/authorisation logic changes.
- tests/test_unhashable_agent_id_s8.py: 32 passed on the head.
- I probed the sibling the PR leaves alone (the card assigns `payload.token_id` to S6-12): on the head, a `lifecycle.expiring_authority` event with `payload.token_id = ["x"]` still makes `build()` raise `TypeError: cannot use 'list' as a set element` (HIGH, run by me). So /pack can still 500 through that key until S6-12 lands.
- Full attestation-reporter suite (PR: 287) not run by me.

## Mutants (engine.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | canary guard removed (hash the id) | RED (31 failed) |
| M2 | distinct-agents guard removed | RED (16 failed) |
| M3 | canaries never excluded | RED |
| M4 | key becomes `str(agent_id)` (odd ids counted) | RED |
| M5 | key always None | RED |
| M6 | canary test uses `str(agent_id)` | equivalent (a list's str can never equal a canary id); not counted |
Totals counted from the table: 5 real mutants, 5 RED, 0 SURVIVED; 1 equivalent excluded.

## LOWs (optional, new PR)
1. The token_id 500 above stays open until S6-12; a test that pins "pack builds with an odd token_id" belongs with that card (not this PR).
2. Registry and token `transform` lambdas were not audited for other non-string field uses (the author says so); the 3 x 5 matrix in the tests exercises agents, tokens and ledger answers with odd `agent_id` only.
