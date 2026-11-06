VERDICT: PASS on 2fef9a2c5e4baae4ceb8d510c7656b8fa0b966ab  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for my PASS WITH CONDITIONS on faaab269. My required condition C1 (a health test that can fail) and my optional C2 and C3 are met; the standing GX10 and CI gate stays open.

R-PR854-2fef9a2, PR 854 (S2-4 / R-1: kill-switch identity revoked or unreadable fails loudly; Stage 2 rehearsal script). Applies to this head only. The fetched pull/854/head is 2fef9a2c; the delta from the reviewed head is two commits (a test file change and the runbook step wording), git diff faaab269..head: 2 files, 33 insertions, 10 deletions. No service code changed. Nothing under .github/. Base 250154d3 is 14 commits behind main; `git merge-tree --write-tree origin/main <head>` is clean (tree id only).

OBJECTIONS FIRST
1. Mutant R2 (the registry's on_behalf_of honoured for any authenticated caller, not only one holding bypass_operator_list) still SURVIVES the new file (9 passed). The builder argues, and the new test documents ("Honest limit"), that the mutant is equivalent in what a caller can observe because the ledger side (bind_on_behalf_of and the reserved-key merge) drops the name independently. I checked what the new test asserts, not the whole ledger path: with a non-bypass identity sending the header, the 200 response stands and the ledger row carries no operator_on_behalf_of and names the authenticated id `don`; that passes under the mutant, so the two layers are redundant for this observable. Accepted as an honest limit: the registry-side gate is no longer pinned on its own, only the combined result. LOW. HIGH on the survival, MEDIUM on "equivalent" (I did not mutate the ledger layer to confirm it is the only other gate).
2. The runbook now says the kill-switch's OWN refused_count does not move ("its guard accepted Don's key") while the registry's does. The tests assert only the registry's count rises by exactly one. I measured the other half by hand on this head (same stack, in-process): before the kill, registry refused_count 0 and kill-switch 0; the kill answered 502; after, registry 1 and kill-switch 0. So the runbook sentence is true, but it is not pinned by a test. LOW.
3. The OFF/LOG-ONLY test now revokes the key in both modes (the "off" case previously never revoked it); fixed from my earlier objection 5. HIGH.
4. Unchanged: the tests still show the kill answers 502 with the record unchanged and no halt signal, so the agent keeps running; the docstring and runbook now say "FAILS LOUDLY ... until B-7 or B-1" instead of "fail closed" (my earlier objection 2). HIGH.

ASSUMPTIONS
A1 The 502 wording regex in the test (`registry unreachable — cannot (kill|revive): registry returned (401|403)`) is the real server text; it passes on the head, so it matches. A2 My earlier mutants K1 to K5 and R1 are still the right product mutants; the new ones below were added for the changed tests.

REASONING / CHECKS
1. Diff read in full (faaab269..head): the health test now reads the registry /health `refused_count` before and after one refused kill and asserts it rose by exactly 1 (replacing the string-count escape); the 502 wording is a full-match regex per verb; two assertions that no `kill.agent` and no `kill.revive` event exists after the refused attempts; a new negative test (a non-bypass identity naming `someone-else`: 200, no operator_on_behalf_of in the payload, authenticated id `don`); the OFF case revokes the key too; docstring and runbook wording say the kill fails loudly. HIGH.
2. Identity: 2 of 2 new commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, kill-switch, agent-registry, sealed-ledger and field-core src on PYTHONPATH): the new file 9 passed, 0 failed (83 s). I did not run the whole kill-switch suite. HIGH.
4. Mutants on a copy of the head, the new file only, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| K1 | kill: a registry error on the flip swallowed (fail open) | KILLED |
| K2 | revive: a registry error on the flip swallowed | KILLED |
| K4 | kill flip error answers 503 instead of 502 | KILLED |
| K5 | revive flip error answers 503 instead of 502 | KILLED |
| K6 | kill flip error text "cannot kill" -> "cannot stop" (the exact-wording pin) | KILLED |
| R1 | registry: on_behalf_of never honoured (break-glass refused) | KILLED |
| H3 | registry refused_count never incremented (the health pin) | KILLED |
| R2 | registry: on_behalf_of honoured for any authenticated caller | SURVIVED (objection 1) |

Counted from the table: 8 run, 7 KILLED, 1 SURVIVED, 0 NOT APPLIED. My earlier health-test mutants H1 and H2 (mutations of the test itself) are moot: the old assertion is gone. The health test now has a product mutant (H3) that kills it, which is the point of my previous C1. HIGH on the counts.

CONDITIONS
C1 (standing gate) GX10 16/16 and CI on this exact head; not run by me. After this PASS the head is frozen.
C2 (optional, new PR) pin that the kill-switch's own refused_count stays at 0 in that scenario (runbook step 4), and, if the two on-behalf-of layers are meant to be independent defences, a test per layer.

NOT VERIFIED
The full kill-switch suite, GX10 / Linux, CI, the rehearsal on an estate (deployer work), whether the ledger layer is the sole other gate behind R2.

CONCLUSION
All three of my earlier conditions are fixed: the health pin is real (it dies when the counter is not incremented), the 502 wording and the absence of kill.* rows are asserted exactly, the negative on-behalf-of case is covered as far as is observable, and the wording now says the kill fails loudly. 7 of 8 mutants die; the survivor is a documented redundancy. PASS on 2fef9a2c; the GX10 and CI gate remains the coordinator's.
