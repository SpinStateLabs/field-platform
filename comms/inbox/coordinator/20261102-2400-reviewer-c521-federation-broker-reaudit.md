VERDICT: PASS WITH CONDITIONS on main b929f12 (federation-broker re-audit after PR 300, C-470)

Card C-521 (standing post-merge re-audit, services/federation-broker, one active contract per org, merged a9dc4f3), Lane 7. Read first, as the card says: my PR 300 report (20261102-0830) and my PR 306 report (20261102-1100); I tested what they did not. Main at the time: b929f12 (a9dc4f3 plus PR 310's allowlist). Not run on the GX10 (cloud session). Findings become cards; the coordinator numbers them.

Conditions: the two findings C-483 already names are still open on main and reproduce (F-C521-1, F-C521-2); and contract writes leave no ledger record (F-C521-3, new).

OBJECTIONS (before evaluation)
1. A rule that is correct for the exact string can be undone by every other spelling (C-483 F-PR300-1).
2. A SELECT-then-INSERT is not atomic across processes (C-483 F-PR300-2); in one process the lock must hold under threads.
3. A governance write (a contract decides what may cross) with no audit trail cannot be reconstructed.
4. An org name with no hygiene is echoed into reasons and ledger events.
5. `INSERT OR REPLACE` lets one write move a contract to another org or strip its key.

ASSUMPTIONS
A1. Reads are behind the perimeter secret only (`install_authn(app)`); writes by `guard_federation` (the operator guard). My fixture runs the guard in its default mode, not ENFORCE.
A2. One writer process in production: the CLI goes through the HTTP API and `fedbroker serve` runs one uvicorn process (cli.py:70-102, :204-208).

REASONING
1. Suite: the whole federation-broker suite on main b929f12: 105 passed (95 earlier tests plus the 10 of PR 300) (HIGH, run).
2. Mutants, named with the test that kills each (hand, 11 that compile, whole broker suite, first failure shown): guard on always and `if not active` and guard removed: test_an_inactive_second_contract_is_accepted_but_cannot_be_activated_beside_an_active_one and test_a_keyless_contract_beside_a_keyed_one_for_the_same_org_is_refused; self-exclusion dropped: test_concurrent_reads_and_writes_return_the_right_contract; inactive rows counted: the inactive-second-contract test; `for_org` ORDER BY dropped and reversed: test_a_legacy_database_with_two_active_rows_resolves_to_the_lowest_contract_id_every_time; 409 as 422 and the API not catching `ContractConflict`: the keyless-beside-keyed test; the keyless guard moved after the scope check: test_the_keyless_guard_decides_before_the_scope_check. All 11 red. (A twelfth, moving the check outside the lock, did not compile as a mutant; the lock is pinned by test_every_connection_use_in_the_store_holds_the_lock.)
3. F-C521-1 reproduced on main (the card's first item): with an active contract for "Borealis Example Corp", PUT /contracts/<new id> for each of these orgs answered 200 (a second active contract): lower case, trailing space, upper case, two spaces, "Boreális" with a composed accent, the same with a decomposed accent, a zero-width space, a "Bořealis" lookalike, the full-width "Ｂ", a no-break space, a tab. 11 of 11 accepted (HIGH, run). Consequence is bounded: `for_org` matches the exact string, so a crossing that names a variant finds only that variant's contract (no contract means BLOCK), so this is not an allow bypass; it breaks the rule's stated goal of one contract per org and lets two contracts for one real organisation carry different scopes and keys.
4. F-C521-2 reproduced on main (the card's second item): two ContractStore objects on one file, the second saving a different-id active contract inside the first one's check-to-insert window: afterwards both rows are active (HIGH, run). Within one process the lock holds: 16 threads times 25 distinct ids for one org: 1 save succeeded, 399 raised the conflict, 0 other errors, exactly 1 active row (HIGH, run). With one writer process (A2) the race needs a second process on the same file.
5. New: contract writes are not ledgered (F-C521-3). With a recording ledger on the engine, four PUTs (create, move the contract to another org, a second active contract refused with 409, deactivate) produced ZERO ledger events (HIGH, run). Only crossings are ledgered (engine.py ~404-407, "every crossing is a ledger event"). A registration widens or narrows what may cross, and `INSERT OR REPLACE` lets a write under the same id replace the key (a key swap) or remove it (the demo's step 4b does that on purpose): none of that leaves a record. In ENFORCE the guard's own `operator.*` rows record the authentication, not the action.
6. New: org name hygiene (F-C521-4). Only `min_length=1` is enforced: a three-space name, a single zero-width space, a single newline and a 5000-character name were all accepted (200) (HIGH, run). The name is echoed into `reasons` ("no active federation contract with '<org>'") and into the ledger event's `counterparty_org`.
7. Checked and sound: moving a contract into an org that already has an active one is 409, and 200 when the moved contract is inactive; re-registering the same id replaces; the 409 body escapes control characters (it prints the org with `!r`), so a name holding a newline cannot forge a line (HIGH, run). `GET /contracts` needs no operator header (the perimeter secret only), as before; I did not change that finding.

FINDINGS
- F-C521-1 LOW-MEDIUM (reproduced; known as C-483 F-PR300-1): spelling variants each get an active contract. Fix as C-483 says: one normaliser (strip, collapse whitespace, NFKC, casefold) used by `save`, `for_org` and the API; add the 11 spellings above as tests.
- F-C521-2 LOW (reproduced; known as C-483 F-PR300-2): no unique index and a non-atomic check across processes. Fix as C-483: `BEGIN IMMEDIATE` and a partial unique index, built only when the table has no duplicates.
- F-C521-3 MEDIUM-LOW (NEW, PROVEN): no ledger record for any contract write, including a refused one, a move to another org, a replace that changes or removes the key, or a deactivation. Fix: ledger `federation.contract.<registered|replaced|deactivated|refused>` carrying the operator id, contract id, org, active before and after, and key present yes or no (a key fingerprint at most, never the key); same event schema discipline as the rotation events.
- F-C521-4 LOW (NEW, PROVEN): org names are unvalidated (whitespace-only, zero-width, newline, 5000 characters). Fix in the same normaliser: strip, a length cap, refuse control and zero-width characters.
- F-C521-5 LOW (design note): `INSERT OR REPLACE` under one id can change the org and the key in one write; with F-C521-3 closed this is auditable and acceptable.

CONCLUSION: PASS WITH CONDITIONS on main b929f12. The PR 300 rule does what it says, 105 tests pass and 11 of 11 mutants are red with named killing tests; the two findings C-483 holds are real and still open, and one thing no reviewer had checked, the audit trail of contract writes, is empty. Whole suite on the GX10 not run by me.

What I did NOT do
- Not run on the GX10 (cloud session); local Python 3.13 only.
- Did not run a cross-process race with real uvicorn processes (two stores on one file stand in for it).
- Did not exercise the operator guard in ENFORCE mode (my fixture uses the default), so the `operator.refused` rows for a refused write were not probed.
- Did not read the ledger side of crossing events or the sentinel; did not run the tools suite (nothing under tools/ changed since my last full run on this service).
