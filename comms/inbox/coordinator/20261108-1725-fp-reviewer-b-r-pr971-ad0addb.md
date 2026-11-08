# Review R-PR971-ad0addb
**VERDICT: PASS** for head ad0addb0c4349286b310f16c32dadfb047a07b14 (S11-6, alerts.py docstring names alert_senders and all seven classes; pin test)

Reviewer: fp-reviewer-b. Independent (did not build this PR).

## Checks
| Check | Result | Confidence |
|---|---|---|
| Head equals PR head | yes | HIGH |
| Author and committer | Don Hagell 13129187+dhagell noreply, 1 commit | HIGH |
| Files | alerts.py (+5/-5, docstring only), tests/test_alerts_docstring_callers.py (+20); 0 under .github/ | HIGH |
| Secrets / estate addresses | none | HIGH |
| Behind main | 32 commits, `merge-tree` clean | HIGH |
| Line count of alerts.py unchanged (hunk -1,10 +1,10) | ENVIRONMENT.md cites alerts.py:79-81 still valid | HIGH |
| Lints (boundary-echo, blindspots, http-env-proxy, no-line-cites, environment-doc, environment-anchors) | 299 passed | HIGH |
| field-core suite | 1931 passed, 3 skipped | HIGH |

## Docstring claims verified against code
- `CLASSES` has seven entries; `SENDERS` has the six production classes (alert_senders.py:101-108); `test` has `alerts.send_test` (cli.py:180). HIGH.
- Callers on main: operator observer (operator_observer.py:597, sends break-glass alerts only) and `tools/stage_controller.py` (stage_transition, stage_aborted). Rotation classes have no call site. HIGH.

## Mutants (scratch copies, new tests, 3 tests)
| # | Mutant | Result |
|---|---|---|
| Q1 | drop `alert_senders` from the opening sentence | SURVIVED (name also appears in "see ``alert_senders``") |
| Q2 | drop stage_aborted from doc | KILLED |
| Q3 | drop rotation_halted from doc | KILLED |
| Q4 | restore "the key rotator (" | KILLED |
| Q5 | restore "the dead-man check (" | KILLED |
| Q6 | drop `test` from doc | SURVIVED (substring "test" occurs elsewhere) |
| Q7 | drop breakglass_used from doc | KILLED |
| Q8 | SENDERS gains `test` | KILLED |
| Q9 | SENDERS loses stage_aborted | KILLED |

Totals: applied 9, killed 7, survived 2, not applied 0. Baseline 3 passed.

## Optional LOWs (new PR, not conditions)
1. Q1 and Q6: the substring-anywhere asserts cannot tell the opening sentence from a later mention; `"test"` is trivially true. Assert on a sentence-level string for the entry-point claim.
2. docs/runbooks/ntfy-alerts.md lines 98-99 and 32 still say stage_transition/stage_aborted have "no controller in this repository" / "no caller on main", while tools/stage_controller.py calls both. The docstring is right, the runbook is stale (MEDIUM: I did not read the controller's wiring beyond the call sites).
