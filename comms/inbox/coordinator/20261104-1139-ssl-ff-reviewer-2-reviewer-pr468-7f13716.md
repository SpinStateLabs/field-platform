# Reviewer report: PR 468 @7f137163 (llm and claude-approver send the perimeter secret alone, C-1181, C-1150 F2 slice C part 4)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator). Security-adjacent (credential headers).

## Verdict: PASS WITH CONDITIONS (head 7f137163b2015af28d822ba74711c878043c9574)
Conditions: C1 rebase on current main (PR base is cddca526, main is 97dcfec1, conflict not checked); C2 GX10 16/16 on the exact rebased head; C3 CI green. No blocking code finding.

## Objections first
1. Other `auth_headers()` callers still ride the env operator pair on non-guarded routes: field-agent `_transport.py:24`, attestation-reporter `api.py:64`, compliance-crosswalk `api.py:218` and `cli.py:131` (grep on this head). The PR is "part 4" of slice C so these may be later parts; I do not know (not in the diff). Not a defect of this PR (HIGH that they exist, I did not read the card).
2. The claude-approver routed branch (an estate with its own secret_file) is untouched and untested here; it reads the file secret and already sends the secret alone (read in the diff context, core.py Estate.headers). Fine by reading (MEDIUM, no test run on it).
3. The new test pins only that the pair is absent and the secret present; it does not pin the self-identity pair (L5), which another suite does (HIGH, run).
4. The claude-approver test suite did not collect in my environment (1 error, a missing module in my cloud env); I could not run the approver's existing tests at this head. The PR's own approver test runs (via tools/tests) (HIGH).

## Scope and identity
3 files: field_core/llm.py (+4/-4, import and one call), claude_approver/core.py (+2/-2), tools/tests/test_perimeter_only_llm_and_approver_c1181.py (new, 49). 1 commit; author AND committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH). Test values are marked made-up (HIGH, read).

## Runs
Baseline (unmutated head): PR test file 3 passed. field-core `-k llm`: 81 passed. Mutants run one at a time (llm.py, claude_approver/core.py, guarded_operator.py); kill = PR test file fails.

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| L1 | llm via gateway | operator pair rides again (auth_headers) | KILLED |
| L2 | llm via gateway | secret not sent | KILLED |
| L3 | llm via gateway | wrong secret value | KILLED |
| L4 | llm via gateway | passthrough header dropped | KILLED |
| L5 | llm via gateway | self-identity pair dropped | SURVIVED by PR test; KILLED by existing field-core tests (3 failed with `-k "llm or identity"`) |
| L6 | llm via gateway | operator id header added | KILLED |
| N1 | llm no gateway | gateway branch always taken | KILLED |
| N2 | llm no gateway | secret sent to every host | KILLED |
| N3 | llm no gateway | gateway test inverted | KILLED |
| N4 | llm no gateway | secret header always present | KILLED |
| P1 | approver non-routed | operator pair rides again | KILLED |
| P2 | approver non-routed | empty headers | KILLED |
| P3 | approver non-routed | None | KILLED |
| P4 | approver non-routed | branch inverted | KILLED |
| P5 | approver non-routed | operator id added | KILLED |
| S1 | shared perimeter_headers | adds the pair | KILLED |
| S2 | shared perimeter_headers | returns empty | KILLED |

Counted from the table: 17 rows (llm via gateway 6, llm no gateway 4, approver non-routed 5, shared 2). KILLED by the PR test 16, SURVIVED 1 (L5, killed by an existing suite, so 17 of 17 by the combined tests). Per behaviour: llm via gateway 5/6 (6/6 combined), no gateway 4/4, approver 5/5, shared 2/2. Kill rate by the PR's own test 16 of 17 = 94%.

## Findings
- F1 LOW (HIGH): L5, the PR test does not pin the self-identity pair; existing tests do. No action.
- F2 LOW (HIGH): objection 1; ask the coordinator which card covers field-agent, attestation-reporter and crosswalk.

## Not verified
Rebase on 97dcfec1; CI; GX10; claude-approver existing suite at this head (collection error in my environment); the C-1181 card text.
