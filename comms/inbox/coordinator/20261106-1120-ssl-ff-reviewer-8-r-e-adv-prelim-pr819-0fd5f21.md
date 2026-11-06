# R-E-ADV-v2-one-liners: PRELIMINARY adversarial pass on PR 819 (not the E-gate verdict)
Head read: PR 819 @ 0fd5f21470465a312699f6da6504f67f4e3b9efd (docs/capstone-evidence/v2-one-liners.md, tools/check_one_liners.py). Reviewer ssl-ff-reviewer-8.
The card says it starts after PR 819 merges and B-E1-fu-819-public-wording is in. Neither has happened (PR 819 is OPEN; the follow-up is an unclaimed builder row), so there is no final head and I am NOT issuing the verdict. I am releasing the claim (reason: preconditions not met) so the final pass can be claimed on the merged text. Findings below are on the current head and the test side of them will not change with the wording follow-up.

## Findings (word versus cited test)
### P-1 MEDIUM (confirmed): row 3 (Delegation Authority) claims more than its citations prove
New wording: "for registered, active agents, minted and revoked ledger-first".
- "only for registered, active agents" cites `test_delegation_authority.py::test_mint_refused_for_killed_agent`, which proves one case: a KILLED agent gets 409 (`assert r.status_code == 409`). It does not prove "registered" or the other non-active states. Tests for those exist and are not cited: `test_delegation_authority.py:91 test_mint_refused_for_unregistered_agent`, `test_redteam_mint_matrix.py:243 test_unregistered_agent_is_404`, `:257 test_a_retired_agent_cannot_be_reactivated_so_mint_stays_refused`.
- "revoked ledger-first" has NO citation at all: the only ledger-first test cited is for mint (`test_adversarial_ledger_down_mint_fails_closed`: 502, "refusing to mint", no token stored). A revoke test exists and is not cited: `test_revoke_c625.py:70 test_a_revoke_while_the_ledger_is_down_is_refused_502_and_the_token_stays_active`. As written the doc states "revoked ledger-first" as Enforced-adjacent wording without proof.
Fix direction: cite those tests (or drop "and revoked"/"registered").

### P-2 LOW (confirmed): the checker proves existence and a token mention, not that the test asserts the word
`tools/check_one_liners.py` passes 404/404 on this head (run by me): commit exists, file exists at it, function exists, KEY token appears in the test source. A key token that is only a fixture value or call argument passes. My AST heuristic found 23 of 95 Enforced citations where the KEY token is not inside an `assert` of the cited test (listed by the script `cite_audit.py` in my scratchpad). Most are benign (the token is an argument to the call under test). I read six and they hold: governed decorator ("must never run" is asserted by `calls == ["ran"]`), signer required (`pytest.raises ... match="no pack ships without a named signer"`, zero asserts but a raises), auto-kill flag off (orphan stays active), ledger-down mint (502 and empty token list), killed-agent mint (limited, see P-1), sentinel enforce blocks. The other 17 flagged citations I did not read.

### P-3 informational: every cited test runs and passes
All 90 unique cited test ids, run at this head in a Windows venv, grouped by service: agent-registry 9, attestation-reporter 6, compliance-crosswalk 11, delegation-authority 8, federation-broker 7, force-gateway 7, incident-replay 7, kill-switch 8, lifecycle-manager 5, sealed-ledger 11, spend-governor 7 passed; conformance-sentinel 10 passed when run from its own service directory (its tests import `tests.*`; run from the repo root they error at collection, which is how I first saw "4 errors"). No cited test carries a skip, xfail, platform guard or module `pytestmark` (script `cite_audit2.py`).

## Not checked (stated)
Whether each of the other ~80 Enforced words is fully proven by its single cited test (I read 6); the Declared words and the REWORD reasons for truth; rows 4 to 12 wording against the code; the global line and all "both estates" wording, which the follow-up replaces; the checker's behaviour on a clone lacking the pinned commit (reviewer-7 objection 3 and the follow-up).

## What the final pass should do
After PR 819 and B-E1-fu-819-public-wording land: re-run the checker on the merged file, confirm `grep -n "both estates"` is empty, re-check P-1 is fixed, and read the remaining citations beyond the six I read.
