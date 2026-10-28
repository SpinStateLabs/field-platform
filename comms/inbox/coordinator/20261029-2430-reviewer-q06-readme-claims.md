# Q-06 reviewer report: "Enforced in code" rows of the service and package READMEs against the tests and against my mutation findings

VERDICT: every test name the READMEs cite exists (260 of 260); one cited test FILE does not (1 of 144). Of 285 "Enforced in code" rows, 170 cite a test or file; 115 cite none. The rows that overstate what the code pins are the ones my mutation and probe rounds already found; they are listed with their finding ids.

OBJECTIONS FIRST
1. A cited test that exists is not a test that pins the claim: only mutation shows that, and I mutated about a third of the services.
2. "Cites no test" is a regex judgement on the row text (no test_*, tests/, .py, "(test)" or the word "tests"); some of the 115 name the mechanism instead, which is acceptable for a code reference.
3. READMEs were scanned on tree 7b4d6f7 (main 4cf73d5 + the registry guard); no live estate.

ASSUMPTIONS
1. Scanned `services/*/README.md`, `packages/*/README.md`, `defence-shield/*/README.md`: 285 lines containing `**Enforced in code`. Test names extracted from backticks (`test_...`); resolved against every `def test_...` in tracked Python files. [HIGH]

REASONING
1. Cited test names: 260 found as a def or file, 0 missing. Cited test file names (`test_*.py`): 144, 1 missing. [HIGH]
2. LOW, F-Q06-1: `services/spend-governor/README.md:129` cites "conformance-sentinel `tests/test_d1_metering.py`"; the sentinel's tests directory holds `test_throttle_metering.py` (no `test_d1_metering.py`, no other file matching "d1_metering"). A stale file name behind an "Enforced in code (v1.2 D1 + F1/F3)" claim about per-ALLOW metering. [HIGH]
3. Rows citing no test or file, by README (count, first line): packages/field-agent 4 (:78), packages/field-core 4 (:42), attestation-reporter 1 (:184), compliance-crosswalk 2 (:248), conformance-sentinel 3 (:212), delegation-authority 2 (:207), federation-broker 5 (:95), force-gateway 2 (:242), incident-replay 2 (:69), kill-switch 2 (:98), lifecycle-manager 3 (:199), ops-console 4 (:48), sealed-ledger 2 (:539), spend-governor 4 (:125). These are candidates for a "name the test" pass; I did not judge them one by one. [MEDIUM]
4. Rows I found to exceed what the code or tests enforce (each is already in the register): compliance-crosswalk "No fabricated regulation citations can ship" (F-R16-2, fixed in PR 89) and "Only FC-E-04 cites anything" (F-R16-1, fixed); agent-registry/kill-switch "no transition out of retired ... for every identity" (F-C155-1: false with the operator layer OFF until PR 90/91); defence-shield read-only/no-network structural claims not gated by CI (F-C141-1) and its structural test red (F-C141-2); defence-shield "listed, never suppressed" vs the exit status (F-C141-3); claude-approver: no README line says an ALLOW authorizes a tool name only (F-C156-1) and the halt marker is Declared (F-C156-2); conformance-sentinel: the mode default and typo behaviour (F-C157-3), the governor non-200 guard (F-C157-1); federation-broker: keyed contracts only (F-R09-1, F-R09-2). [HIGH on the ids; each row's wording is quoted in its own report]
5. Not done: mutation of the other services' claimed guards (ops-console, force-gateway, sealed-ledger store claims, lifecycle-manager beyond R-12); a row-by-row read of the 115 untested-looking rows.

CONCLUSION
Fix the one stale filename (F-Q06-1) and add test names to the 115 rows over time; the register already holds the overstated rows with fixes in flight.
