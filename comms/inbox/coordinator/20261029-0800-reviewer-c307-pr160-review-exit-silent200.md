# C-307 reviewer report (Lane 5): PR 160 agent-incident-retro tests: REVIEW-only exit and S.silent-200 boundaries @e277237e2af006c85f43e5278b27f5e5f26aff4e (C-300; my C-290 P1/P2)

VERDICT: PASS on the exact head e277237e2af006c85f43e5278b27f5e5f26aff4e. Both findings from C-290 are closed: the mutant `Exit(2 if ESCALATE or REVIEW else 0)` now dies, and the six S.silent-200 mutants I named (hostile filter `and` to `or`, hostile filter dropped, `< 300` to `<= 300`, `200` to `199`, `200 <=` to `<`, clause forced to None) all die. Full gx10_verify is green. Class and file:line only; no values.

OBJECTIONS FIRST
1. The new file imports its helpers from the C-148 test file (`from test_detection_pins_c148 import SQLI, req, sess`). That file is on main (b099b28), so it works today; if the C-148 file is renamed or moves, this one breaks at import. LOW. [HIGH, read]
2. It pins what the code does today: a REVIEW-only log (a hostile request answered 404 or 200 with no other clause) exits 0, and 300 is not a silent 200. Decisions, not proofs of correctness. [HIGH]
3. P3 of C-290 (pivot internals at clauses.py:155 and :166, the feature counters) is not in this PR's scope and remains open; defence-shield still is not in CI (C-141 F-C141-1). [HIGH]

ASSUMPTIONS
1. One commit on main a946d26; author and committer Don Hagell noreply; one new file defence-shield/agent-incident-retro/tests/test_review_exit_and_silent200_c300.py (+93, 16 cases). [HIGH, run]

REASONING
1. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr160, base f75baab, so the counts include the stack since that base): core_services 2244 passed 4 skipped; tools 2082 passed 3 skipped; agent-registry 277; sentinel 111; incident-replay 91; crosswalk 162 (1 skipped); gateway 257; lifecycle 212; attestation 66; ops-console 222; claude-approver 162; field-agent 150; topology_lint OK; EXTRA defence-shield 182 passed (166 plus the 16 new). VERDICT CI-EQUIVALENT STEPS GREEN. [HIGH, run]
2. What the tests assert: a REVIEW-only scan (a SQL-injection-shaped request answered 404, and answered 200) prints `ESCALATE 0 · REVIEW 1`, exits 0, and still writes the report; REVIEW plus an escalating request in the same log exits 2; `s_silent_200` returns a hit only for a hostile request answered 200, 204 or 299, and none for 199, 300, 302, 404, 500, and the hit's clause id is `S.silent-200`. [HIGH, read and run]
3. Mutants (36 on clauses.py 200-225 and cli.py 60-100, 16 hand, run with bytecode caching off): the new file alone kills 13. Relevant to the two findings: the REVIEW-exit hand mutant killed; the six silent-200 hand mutants killed; the generated mutants on clauses.py:204-212 (the clause's guard, return values, status constant) all killed. The survivors are on other clauses and the CLI parser (clauses.py:221-224, the cadence clause; cli.py:67-80, option handling and the unparsed-ratio check), outside this PR. The old allowlist hand mutants in my config survive this file alone by design: the C-148 file kills them (C-290: 15 of 16, the 16th is the REVIEW one now closed). [HIGH, run]
4. Public-repo hygiene: the fixture uses a documentation-range address; no address of an estate, flag value or secret. [HIGH, read of the file's constants]

CONCLUSION
PASS on e277237. C-290 P1 and P2 closed; no new cards. Still open from C-290: P3 (LOW, pivot internals and feature counters) and P4 (defence-shield in CI).

What I did NOT do: mutate the rest of the module; check that the REVIEW-only result is what the owner wants for a scheduled alert (a policy decision, C-141).
