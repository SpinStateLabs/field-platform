# Reviewer report: PR 450 @483e3f4b (Phase E "the words": v2-one-liners, E-gate, wording; PR 308 rebuilt, C-1159)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13. 24 files, +957/-60, 9 commits. One code file (tools/e_gate.py, +301) with tests/test_e_gate.py (+164); the rest is wording in public docs, one new evidence file, and small edits to demo and fly scripts.

## Verdict: PASS WITH CONDITIONS (head 483e3f4bdd7c15fe65d817c38a434fa1d33bb541)
Conditions: C1 rebase on current main (PR base is 05942b98; `git merge-tree` of main 97dcfec1 with this head shows no textual conflict, but that is not a rebased test run); C2 GX10 16/16 on the exact rebased head and CI green (the gate runs `git merge-base --is-ancestor` on cited commits, so CI needs a full-history checkout; see objection 1); C3 the wording changes are Don's call on content, not mine: I checked structure and gates, not whether each public sentence is the right claim. No blocking code finding.

## Objections first
1. The gate fails in a shallow clone: with my default shallow fetch `python tools/e_gate.py` printed 80 "commit ... is not an ancestor of HEAD" failures; after `git fetch --unshallow` it printed `E1: 12 systems, 80 Enforced citations, 40 Declared rows checked` and `E-GATE: PASS (0 problems)` (HIGH, run). Any CI job or session with depth-limited checkout will report a false FAIL. The PR does not wire the gate into CI (not in the diff); if the coordinator does, the checkout needs `fetch-depth: 0`.
2. The unit tests stub git, so the real ancestry walk is only exercised by running the tool (HIGH, read). I ran it: PASS on the PR head.
3. A gate that reads test source cannot prove the test passes; it proves a named test with an assertion naming the keyword exists at the cited commit (HIGH, read of the docstring: "every Enforced word cites a test that exists and says it"). A cited test that fails in CI is outside this gate.
4. Eight structural checks have no failing fixture (P1 to P8 below): the global status line, numbering 1-12, six-cell rows, both kinds per system, sha shape, test_ prefix, the Declared reason length and estate-status "Declared". If one is deleted the shipped-file test still passes (HIGH, run).
5. The commit message and todo note state "tools/tests count at 48acfa6 is 2,810, total 8,090": I did not recollect at that commit (not verified).
6. Public-safety scan of added lines: no fly.dev host, no IPv4, no flag assignment, no credential pattern (grep, HIGH). I did not read all 957 added lines as prose.

## Identity
All 9 commits: author AND committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH).

## Runs
Baseline (unmutated head): tools/tests/test_e_gate.py 18 passed; `python tools/e_gate.py` PASS after unshallow (see objection 1). Mutants edit tools/e_gate.py one at a time; kill = test_e_gate.py fails; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| S1 | assertion words | bare string statements counted as words | SURVIVED, EQUIVALENT (a bare-string statement cannot occur inside an assert or raises node that `_words` is called on) |
| S2 | assertion words | pytest.raises blocks ignored | KILLED |
| S3 | assertion words | words taken from the whole test | KILLED |
| S4 | assertion words | every test counts as asserting | KILLED |
| S5 | assertion words | bare `raises()` not recognised | SURVIVED (F1) |
| S6 | assertion words | keyword check removed | KILLED |
| S7 | assertion words | Name nodes not collected | KILLED |
| S8 | assertion words | constants not collected | KILLED |
| D1 | defines | prefix match accepted | KILLED |
| D2 | defines | always true | KILLED |
| D3 | defines | commit definition check removed | KILLED |
| A1 | ancestor | check removed | KILLED |
| A2 | ancestor | direction reversed | KILLED |
| N1 | negation | up to 40 words before | KILLED |
| N2 | negation | only immediately before | KILLED |
| N3 | negation | "a" counts as a negation | SURVIVED (F2) |
| N4 | negation | negation anywhere on the line (the old bug) | KILLED |
| N5 | negation | no exemption at all | KILLED |
| N6 | negation | "compliant with" not banned | KILLED |
| N7 | negation | "certified" not banned | KILLED |
| R1 | readme cross-check | Enforced-vs-Declared check removed | KILLED |
| R2 | readme cross-check | Declared-vs-Enforced check removed | KILLED |
| R3 | readme cross-check | missing README row accepted | SURVIVED (F3) |
| V1 | verbatim old sentence | check removed | KILLED |
| P1 | probe | estate status must be Declared | SURVIVED (F4) |
| P2 | probe | Declared row must state a reason | SURVIVED (F4) |
| P3 | probe | cited function must start with test_ | SURVIVED (F4) |
| P4 | probe | sha must look like a hash | SURVIVED (F4) |
| P5 | probe | table row must have 6 cells | SURVIVED (F4) |
| P6 | probe | each system needs both kinds | SURVIVED (F4) |
| P7 | probe | systems numbered 1 to 12 | SURVIVED (F4) |
| P8 | probe | global estate-status line present | SURVIVED (F4) |

Counted from the table: 32 rows (assertion words 8, defines 3, ancestor 2, negation 7, readme 3, verbatim 1, probes 8). KILLED 20, SURVIVED 12 (1 equivalent S1, 3 in-claim S5/N3/R3 plus the 8 probes). Of the 24 rows covering behaviours the PR text claims to test (everything except the probes), KILLED 20, SURVIVED 4, one of those equivalent: 20 of 23 non-equivalent = 87%. Per behaviour: assertion words 6/7 non-equivalent, defines 3/3, ancestor 2/2, negation 6/7, readme 2/3, verbatim 1/1, probes 0/8.

## Findings
- F1 LOW (HIGH, run): S5. Add a fixture with a bare `raises(...)` import.
- F2 LOW: N3 is a contrived mutant; skip unless cheap.
- F3 LOW (HIGH, run): R3. No fixture for "README row not found".
- F4 LOW to MEDIUM (HIGH, run): eight structural checks (P1 to P8) have no failing fixture; add one parametrised "delete this line, expect this message" test.
- F5 LOW: objection 1; document `fetch-depth: 0` if the gate goes to CI.

## Not verified
Rebased run on 97dcfec1; CI; GX10; the 2,810 / 8,090 counts at 48acfa6; whether each reworded public sentence is the right claim (Don's call).
