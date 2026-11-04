# Reviewer report: PR 588 @5747f7ec (kill-switch: an unreachable registry on /heartbeat and /drill is 502, not an unhandled 500, S2-1)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator). Two commits: kill_switch/api.py (+8) and tests/test_heartbeat_registry_unreachable.py (new, 83).

## Verdict: PASS WITH CONDITIONS (head 5747f7ec150ef544e1de0d6cd1ac99732c8b291e)
Conditions: C1 rebase check: the PR base is 97dcfec1, main is b963407a; `git merge-tree` shows a clean tree (022e9daa), the rebased head is not run; C2 GX10 16/16 on the exact head and CI green; C3 the coordinator or Don confirms the semantic choice in objection 1 (it is a behaviour change in a safety service). No blocking code defect.

## Objections first
1. Behaviour change: an unreachable registry on `GET/POST /heartbeat/{id}` used to be an unhandled 500; it is now a 502, explicitly NOT killed=true and NOT killed=false ("the caller decides", code comment). The field-agent SDK describes a fail-closed heartbeat; a 502 reaches it as an unreachable heartbeat, which that SDK treats as a failure (I did not re-read the SDK here: MEDIUM). If any other caller treats any non-200 as "alive", the change moves from an error to a decision (MEDIUM, not run).
2. The drill: after the kill write succeeds and a later registry read fails, the `finally` restores the status; if the registry is still down the restore fails, `restored` goes false, a `kill.drill.restore_failed` note is written, but the caller gets a bare 502 and the record stays `killed` with no report. The tests cover only "the kill write fails first" (agent stays active) and "reads down at the start"; the "killed and not restorable" path is untested in this file (HIGH, read of the drill body and the test file).
3. Retired-agent and unregistered-agent behaviour is unchanged: unknown agents still read killed=true on /heartbeat (fail closed) and the drill still refuses a retired agent with 409; the PR touches neither (HIGH, read of the diff context).
4. Reply text: the three 502 details are fixed phrases (the second commit exists for that). The new test file asserts only that "registry unreachable" appears in the detail, so an echo of the exception text passes the file (H4, D3, K3 below); the repository's boundary-echo lint catches the echo shape (I ran H4 against it: `test_boundary_echo_scan_matches_allowlist` fails) (HIGH for H4, MEDIUM for D3 and K3, same shape, not run).
5. The f-strings in the three raises have no placeholders; harmless, a lint nit (HIGH, read).

## Scope and identity
2 files, 2 commits; author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH).

## Runs
Baseline (unmutated head): the new test file 5 passed; full kill-switch suite 275 passed. Mutants edit services/kill-switch/src/kill_switch/api.py one at a time; kill = the new file fails; survivors also run against the full kill-switch suite; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | New file | Other tests |
|---|---|---|---|---|
| H1 | heartbeat 502 | handler removed (500) | KILLED | n/a |
| H2 | heartbeat 502 | status 500 | KILLED | n/a |
| H3 | heartbeat 502 | status 503 | KILLED | n/a |
| H4 | heartbeat 502 | exception text in the reply | SURVIVED | full kill-switch suite survived; the boundary-echo lint KILLED it |
| H5 | heartbeat 502 | outage reads as killed=false | KILLED | n/a |
| H6 | heartbeat 502 | outage reads as killed=true | KILLED | n/a |
| H7 | heartbeat 502 | detail lacks "registry unreachable" | KILLED | n/a |
| D1 | drill read 502 | first read handler removed | KILLED | n/a |
| D2 | drill read 502 | status 500 | KILLED | n/a |
| D3 | drill read 502 | exception text in the reply | SURVIVED | full suite survived; lint not run (same shape as H4) |
| D4 | drill read 502 | status 404 | KILLED | n/a |
| K1 | drill write 502 | handler removed | KILLED | n/a |
| K2 | drill write 502 | status 500 | KILLED | n/a |
| K3 | drill write 502 | exception text in the reply | SURVIVED | full suite survived; lint not run (same shape) |
| K4 | drill write 502 | wrong exception class caught | KILLED | n/a |
| K5 | drill write 502 | detail lacks "registry unreachable" | KILLED | n/a |
| F1 | drill restore | the finally no longer restores | KILLED | n/a |
| F2 | drill restore | restore failure no longer swallowed (only KeyError) | SURVIVED | KILLED by the full suite (2 failed) |
| F3 | drill restore | except order swapped (AgentNotRegistered and RegistryUnreachable) | SURVIVED, EQUIVALENT (distinct classes) |

Counted from the table: 19 rows (heartbeat 7, drill read 4, drill write 5, drill restore 3). By the new file alone KILLED 14, SURVIVED 5. With the other tests: F2 killed by the suite, H4 killed by the boundary-echo lint; D3 and K3 are unconfirmed (probably the lint), F3 equivalent. Kill rate by the new file on non-equivalent rows 14 of 18 = 78%. Per behaviour: heartbeat 6/7, drill read 3/4, drill write 4/5, drill restore 1/2 non-equivalent.

## Findings
- F1 MEDIUM (HIGH confidence, read): objection 2, the persistent-outage drill that leaves the agent `killed`: no test. A rig where reads work, the kill write succeeds and the restore write fails would pin that the reply is 502 and a `restore_failed` note is written.
- F2 LOW (HIGH, run): H4, D3, K3, the new file does not assert the detail text exactly (`detail == "registry unreachable — cannot read heartbeat"` would pin all three).
- F3 LOW: objection 5.

## Not verified
Rebased run on b963407a; CI; GX10; the SDK's reading of a 502 heartbeat; D3 and K3 against the lint.
