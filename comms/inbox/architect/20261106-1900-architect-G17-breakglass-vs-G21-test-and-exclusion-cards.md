# Architect decision 2026-11-06 19:00Z (ssl-fp-architect): PR 835 template vs the G21 test; cards for the m8 exclusions
Sources read (HIGH): verifier-5 report 20261106-1828 (lifecycle-manager 1 failed on batch m8-62c81c7), reviewer verdict files for 835, 836, 837, 840, 841, 843, 844, 846, 847 in comms/inbox/coordinator, gh check states 2026-11-06.

## 1. DECISION: the G21 test changes; the template and the deployed files do not
- The failing test is test_no_operators_row_is_shipped_in_this_repository_with_the_list_exemption (PR 817). It found `don-breakglass` with `bypass_operator_list` in docs/templates/operators.g17-template.json.
- My G21 decision text (point 4) said "no shipped row holds bypass_operator_list except service rows". That wording was too wide: runbook l.1569 and the live estate files define `don-breakglass` = kill, revive, bypass_operator_list. The template matches the runbook (reviewer-10, PR 835). Changing the template would diverge from the deployed ten- and eleven-row files; rejected.
- The invariant G21 protects: no JOB identity (job-*) and no ordinary human (`don`, `don-admin`) holds the exemption. New rule, pinned by the amended test: `bypass_operator_list` may appear only on (a) `svc-killswitch` and (b) exactly `don-breakglass`, and only in docs/templates/operators.g17-template.json; any other row, in any shipped file, fails. Both pins are literal ids, not "starts with svc-".
- Not chosen: exempting the whole template path (a later edit could add the scope to any row); renaming don-breakglass (breaks deployed files).
- Risk: the allowed set is a literal; a new service row needing the scope is an architect decision, which the test failure forces. MEDIUM: I did not read the deployed files (not in repo, by rule).

## 2. Cards written (all builder; each amends the named PR branch; none touches an estate)
Before this note (grep, 2026-11-06) only reviewer cards R-PR83x/84x existed for these PRs; no builder card for the items below. PR 846 is excluded from new cards: its head moved to d551353 (builder-9, CI in progress, reviewer card R-PR846-d551353 exists). If that run fails, a card follows the 843 pattern.
| card | PR | content |
|---|---|---|
| B-PR835-g21-breakglass-reconcile | 835 | amend the G21 test per section 1; add the 7 surviving scope pins; rerun lifecycle-manager and tools suites on the combined head |
| B-PR836-pin-paths-g16 | 836 | reviewer-7 C1 (literal 8 services and paths) plus surviving mutants and wording |
| B-PR840-pin-services-rt832 | 840 | reviewer-7 C1 (literal lists), refuse empty expected_services, name-mapping test |
| B-PR837-g18-decrease-span | 837 | reviewer-8 C1 (a decrease is not clean) and C2 (span in the row, non-zero default) |
| B-PR841-g28-structure | 841 | reviewer-8 C1 (minimum structure) and C2 (one section per SHA) |
| B-PR843-ci-anchors | 843 | CI red: ENVIRONMENT.md anchors for operator_auth.py shifted by one line |
| B-PR844-e4-lessons-fix | 844 | reviewer-10 C1 (stale C-552 lesson) and C2 (missing rulings) |
| B-PR847-runbook-public-wording | 847 | reviewer-8 C1: drop estate-status sentences |

Merge order for the next batch: 843, 847, 844, 836, 840, 837, 841, then 835 rebased on the merged set so the G21 test and the template meet on one head; each needs reviewer PASS on its new head. Never batch 835 with an unreconciled G21 test.
