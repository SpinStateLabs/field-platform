# Review PR 819 (E1 v2-one-liners + citation checker) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `0fd5f21470465a312699f6da6504f67f4e3b9efd`.
Scope reviewed: the checker (code + tests) and that every citation resolves and runs green. NOT reviewed, and the PR says so itself: whether each cited test actually proves its word, and whether each new wording is true (the E-gate's independent adversarial review). Conditions: (1) that E-gate review happens before the wording is used in README/ROADMAP/decks; (2) coordinator rules on objection 1 below before merge.

## Objections first
1. Public-repo rule vs content: ROLE-LOOP says this repository is public with "no ... deploy status". The file states estate status on every row ("both estates run pre-v1.2 images", "Declared", "unset on both estates", "no estate rotates today"). The architect decision mandates the global line, so this may be accepted; it is the coordinator's call, not mine (MEDIUM).
2. The KEY check is a case-insensitive substring over the test's whole source (name, docstring, body): a trivial key such as "owner" or "conflicts" passes a test that merely names it. Stated limit in the script header; it proves existence, not proof (HIGH, read).
3. The checker pins the commit 3804d0b9 (current main); it fails on a clone without that commit, and has no test against the real file (stated).
4. 95 ENFORCED lines cite 90 distinct tests; several rows reuse one test for different words (e.g. registry row 1: `test_discovery_finds_shadow_agents` backs two words, KEY "shadow" and "bot-crm-enrich").

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. .github/: 0 files. 3 new files (+655): docs/capstone-evidence/v2-one-liners.md, tools/check_one_liners.py, tools/tests/test_check_one_liners.py. No README/ROADMAP/STATE edits. Base == current main 3804d0b9.
- `python tools/check_one_liners.py` on the real file: 404/404 PASS, 0 FAIL.
- test_check_one_liners.py: 36 passed.
- All 90 distinct cited tests, run by me at this head (== main code) per service: agent-registry 5, attestation-reporter 6, compliance-crosswalk 11, conformance-sentinel 9 (10 cases), delegation-authority 8, federation-broker 7, force-gateway 7, incident-replay 7, kill-switch 8, lifecycle-manager 5, sealed-ledger 11, spend-governor 6 (7 cases): 90 ids, every service rc 0, none failing (PR says 96 cases; my case counts: 9+6+11+10+8+7+7+7+8+5+11+7 = 96).
- Spot-verified the PR's own findings: `manifests/canary-gb10.yaml:49` is `endpoint: http://canary-agent:8090/halt` (the plan's "no shipped manifest declares an agent-side endpoint" is indeed false); `services/spend-governor/README.md:129` cites `conformance-sentinel tests/test_d1_metering.py`, which does not exist (the file is test_throttle_metering.py); force-gateway README says the flag is "exactly `1`" (the PR says the code accepts 1/true/yes/on: I did not confirm the code side).
- No estate address, key or secret pattern found in the new file (grep for fly.dev, .ts.net, IPv4, sk-ant, password: 0 hits).

## Mutants of the checker (14; counted from the table)
| # | mutant | result |
|---|---|---|
| K1 | key check always true | KILLED |
| K2 | key match case-sensitive | SURVIVED |
| T1 | test existence unchecked | KILLED |
| F1 | file existence unchecked | KILLED |
| C1 | commit existence unchecked | KILLED |
| G1 | global line unchecked | KILLED |
| R1 | row count 11 | KILLED |
| Q1 | qualifiers unchecked | KILLED |
| M1 | malformed ENFORCED line skipped | KILLED |
| L1 | keyless text unchecked | KILLED |
| P1 | provenance unchecked | KILLED |
| E1 | zero citations ok | KILLED |
| X1 | exit code always 0 | KILLED |
| S1 | class-method tests not found | KILLED |
Totals: 14 mutants, 13 killed, 1 survived (13+1 = 14). K2 is a LOW test gap (case-insensitivity of the key is unpinned).

## Optional LOWs (new PR)
Pin the case-insensitive key; fix the spend-governor README cite to test_throttle_metering.py; the force-gateway README flag text; confirm the code-side 1/true/yes/on claim.

## Not verified
CI on this head; Linux; truth of the new wording; that a cited test proves its word (E-gate).
