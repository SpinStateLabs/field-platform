VERDICT: PASS WITH CONDITIONS on 3285482a2af1bf6538a791c9e68a6355f9e890f8

PR 300 (builder card C-461, reviewer C-355 F-C355-2/-3/-4; no review card existed, Lane 7 took it with a claim line). Production change in services/federation-broker (engine.py, api.py), plus tests, demo.sh and one README line. Head confirmed by PR read: 3285482, one commit; the PR says base 48acfa6; it cherry-picks onto current main 61000ba with no conflict. A PASS applies to this SHA only.

Conditions (two, neither blocks the change from doing what it says): (1) the "one active contract per org" rule is keyed on the exact text of the org name, so a spelling variant gets a second active contract (F-PR300-1); (2) the rule is checked in application code only, with no unique index, so two processes can both win (F-PR300-2). The README and PR text should say what the rule does not cover, or the builder card should close both.

OBJECTIONS (before evaluation)
1. A uniqueness rule on an exact string is bypassed by any other spelling of the same organisation.
2. A check done as SELECT then INSERT is not atomic across processes; a lock in one process does not help a second one.
3. A database that already holds two active rows keeps working, silently, and "which one wins" is a design choice that can be the wrong one.
4. A 409 that names the other contract id returns an id to the caller.
5. A demo that exits 0 proves little unless a wrong verdict makes it exit non-zero.

ASSUMPTIONS
A1. Only one writer reaches the contracts table: `ContractStore.save` is called from api.py:86 only, and the CLI `add-contract` goes through the HTTP API (cli.py:70-102), with `serve` running one uvicorn process (cli.py:204-208). So in production the in-process lock is the only serialisation (HIGH, grep and read).
A2. The caller of PUT /contracts/{id} is an authenticated operator (`guard_federation`), who can already list contracts; the 409 text adds nothing beyond that (MEDIUM: I did not read the guard's scope).

REASONING
1. Tests: the whole federation-broker suite on main 61000ba plus the commit: 105 passed (95 plus the 10 new). Whole `python -m pytest -q tools/tests` in a CI-style venv (pip pinned, constraints files): 2816 passed, 6 skipped, 0 failed (719 s). CI on the exact head: 7 of 7 success. The PR says 105 on Windows and on the GX10; I got 105 on Linux (HIGH).
2. Reading the diff: `save` (engine.py ~303-318) refuses a second ACTIVE contract for an org held under another id (`contract_id<>?` so a re-registration of the same id replaces); inactive contracts skip the check; `for_org` orders by contract_id; the API maps `ContractConflict` to 409 (api.py:82-88). The README sentence matches. Behaviour as stated (HIGH).
3. Mutants (hand, 12, whole suite for each): 10 red / 12. Red: guard always on, guard inverted, guard removed, self-exclusion dropped, inactive rows counted, `for_org` ORDER BY dropped, ORDER BY DESC, 409 to 422, 409 to 400, message not naming the other id. Survivors: the `ORDER BY` inside the new check in `save` (it only changes which of several legacy ids the message names; equivalent for all but a multi-duplicate legacy database) and `ContractConflict(ValueError)` changed to `(Exception)` (equivalent: only the API catches it). The PR's own claim that moving the keyless guard after the scope check is now red: confirmed (1 failed, 104 passed).
4. Demo: `bash demo.sh` run on loopback with the venv the script expects (a temporary link, removed afterwards): exit 0; step 2 ALLOW, step 3 BLOCK F.peer, step 4 outbound ALLOW, step 4b BLOCK F.peer ("holds no counterparty key"), ledger verify true. Three demo mutants (a wrong clause for step 3, a wrong verdict for step 2, a wrong phrase for step 4b) each make the script exit 1 (3 of 3 red). The `|| true` that remain on steps 3 and 4b are followed by the assertion, so they mask nothing; the comment "nothing is masked with `|| true`" at the top of the block reads stronger than that (LOW wording).
5. Probes (made-up orgs, temp databases):
   - Spelling: with an active contract for "Borealis Example Corp", `save` ACCEPTED a second active contract for "borealis example corp", "Borealis Example Corp " (trailing space), "BOREALIS EXAMPLE CORP", "Borealis  Example Corp" (two spaces) and "Borealis Example Corp" plus a zero-width character. All five: no conflict. `for_org` matches the exact text, so each spelling then has its own live contract; the manifest-peer check beside it (`_lists_org`, engine.py ~363-368) is case-insensitive, so the two lookups already disagree on what "the same org" is. Not a bypass of the inbound fail-closed rule (each spelling needs its own registered contract), but the rule's stated goal, one unambiguous contract per org, is not met (PROVEN).
   - Race: two ContractStore objects on one database file (two processes), the second saving a different-id active contract for the same org inside the window between the first one's check and its insert: afterwards both rows are active (PROVEN). The table has no unique index (schema unchanged: contract_id primary key only), so the database does not stop it.
   - Legacy duplicates: for rows "FED-2026-9" then "FED-2026-10", `for_org` returns "FED-2026-10": "lowest contract id" is the lowest TEXT, not the oldest or the numerically lowest (PROVEN). There is no log line at open or at lookup for a database that holds two active rows (PROVEN: no warning in a debug-logging run).
6. The PR chose fail-closed for the legacy case it tested (a keyless row that sorts first blocks inbound rather than letting the keyed row decide). With the text ordering, a keyed row can sort after a stale keyless one and the live, keyed contract is silently ignored (inbound blocked): fail-closed, but invisible.

FINDINGS
- F-PR300-1 LOW-MEDIUM (PROVEN): uniqueness by exact org text; spelling variants each get an active contract. engine.py `ContractStore.save` check (`counterparty_org=?`). Fix: normalise the org for the check and the lookup (casefold, strip, collapse spaces, NFKC) in one helper used by `save`, `for_org` and `_lists_org`; or state in the README that org names are matched exactly.
- F-PR300-2 LOW (PROVEN with two stores): SELECT then INSERT is not atomic across processes and there is no unique index. In production one process writes (A1), so this is latent. Fix: `BEGIN IMMEDIATE` around check and insert, and a partial unique index on (counterparty_org) where active=1 created only when the table has no duplicates, with IntegrityError mapped to 409.
- F-PR300-3 LOW: legacy duplicates resolve silently, by text order. Fix: log a warning at store open and at `for_org` when more than one active row exists for the org, and say "lowest text id" in the README (or order by insertion).
- F-PR300-4 LOW (wording): demo.sh comment "nothing is masked with `|| true`" is stronger than the script (steps 3 and 4b use it before an assertion). No behaviour change.
- No test for the CLI's 409 path (the PR says so). Not a defect; `_fail` prints `error 409: ...` and exits 1 (read).

CONCLUSION: PASS WITH CONDITIONS on 3285482a2af1bf6538a791c9e68a6355f9e890f8. The change does exactly what the PR says: the keyless-beside-keyed probe is now 409, the same id re-registers, inactive contracts are accepted, `for_org` is deterministic, the demo asserts every verdict and goes red when one is wrong, 10 of 12 mutants and the PR's own guard-order mutant are red, the whole tools suite and the broker suite pass, and CI is 7 of 7. The rule can still be satisfied by a spelling variant (F-PR300-1) and, across processes, by a race (F-PR300-2). Coordinator still needs GX10 16/0 on the exact head (the PR says the full GX10 run had only started).

What I did NOT do
- Not run on the GX10 (cloud session); local Python 3.13; other Pythons only through CI. The PR notes the demo cannot run on the GX10 (ports in use); I ran it on loopback in this container only.
- Did not read the guard_federation scope or the ledger side of a crossing beyond what the demo prints.
- Did not read the earlier federation reports (C-355, R-09, C-126) beyond the card text, so a finding above may already be known.
- Did not run mutants of demo.sh beyond three, or of the test file itself.
- Did not examine the 6 skipped tests of the tools run.
