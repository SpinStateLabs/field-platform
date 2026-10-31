VERDICT: PASS WITH CONDITIONS on e5317342aa3288153ef6f8b7a44abba372ce10c9

Reviewer Lane 15, cloud-reviewer, C-979, PR 343 (tools/tests/test_ci_pip_pins_c23.py plus 3 lines in test_yaml_duplicate_keys.py; tests only, no workflow changed). Head e531734, unchanged since Lane 5's C-935 report. UNVERIFIED: no GX10, CI not read; scratch tree.

## Objections first
1. The scanner is a text model of shell, not a shell; its own header says so and states that further spellings are out of scope (test header, "STATEMENT OF SCOPE"). Every shape below that is not caught is either in that list or is the same class; the PASS is for the spellings it pins, not for "no unconstrained install can run" (HIGH).
2. A "reusable workflow" is only half covered: a local callee under .github/workflows is scanned (it is just another file in the glob); a callee or action from ANOTHER repository cannot be, and the header lists it ("a uses: action from another repository, a reusable workflow") (HIGH, probed).
3. A mutant survived by my own try, but my edit hit a different function (it replaced the first "if not installs:", in the older install-step check), so the "blind" check mutant was NOT run; I do not count it. The expression-only run mutant survives and is equivalent: another rule (an expression in command position) flags the same text (HIGH on the run, MEDIUM on equivalence).

## Conditions of C-627, C-730, C-741 at this head
- C-627 F-1 to F-6 (global option before install, order of $C, env and pip config moving the index, expression-only run): closed since 1f93620 per C-741 and C-730; re-probed here for the ones below; the PIP_* env at step level is refused (probe: CAUGHT).
- C-741 F-C741-1 (poetry, pipenv, pip-sync, conda, easy_install, get-pip): an installer set exists (other_installer: poetry, conda, uvx, pipx run, -m build); the builder lists the rest as limits. F-C741-2 (expression plus text, python -c calling pip): python -c subprocess pip is NOT caught (probe) and is listed under "What this does NOT prove" (HIGH). F-C741-3 (share one run-step walker with PR 361's lint): not done (read; two walkers still exist).
- C-730 / C-935 conditions: the builder note claims F-C935-1, -2, -4 closed (arming only as a standalone define; shell allowlist bash/sh/pwsh/powershell/cmd; download/wheel/config rules) and -3, -5 as documented limits. My mutants on those rules are killed (below).

## Workflow shapes the card names (probe: synthetic workflows added to the shipped set)
| shape | result |
|---|---|
| backslash line continuation, unconstrained install | CAUGHT |
| backslash continuation with $C | accepted (correct) |
| matrix value as the install target, no $C | CAUGHT (the install lacks $C) |
| matrix value with $C, one matrix entry a git+https URL | CAUGHT (the URL argument is refused) |
| matrix value with $C and a plain package name | accepted by design: matrix contents are not expanded, so what the matrix feeds is unknown |
| reusable workflow, callee in .github/workflows | CAUGHT (callee scanned) |
| reusable workflow or action from another repository | NOT CAUGHT (cannot be scanned; listed limit) |
| composite action under .github/actions, literal install, input-driven install | CAUGHT both |
| step-level PIP_INDEX_URL | CAUGHT |
| heredoc to bash -s with an install | CAUGHT |
| $P install (variable-named command other than *PIP*) | NOT CAUGHT (listed limit) |
| python -c subprocess pip | NOT CAUGHT (listed limit) |
Control: the shipped workflows pass; a constrained install passes; an unconstrained one fails.

## Mutants on the head (7 applied, 7 killed or equivalent)
Killed: standalone-define arming removed; the download verb removed; composite-action scanning off; the shell allowlist off; the URL-argument rule off; the build-constraint requirement dropped; the nested-statement rule off. Equivalent: the expression-only run branch (objection 3). The 193 tests in the file pass (HIGH, run).

## Evidence
No production or workflow code in the PR. merge-tree with main: 0 conflicts (earlier sweep). Author and committer: the no-reply Don Hagell identity on all four commits.

## Conditions (non-blocking)
1. Follow-up for the one live shape the header does not name: matrix entries (what a matrix can feed an install). 2. Share the run-step walker with PR 361's lint (C-741 F-C741-3). 3. Keep workflow-diff review as the real control, as the header says.

Not verified: CI, GX10, the "blind" check mutant, whether every shipped install spelling in other workflows exists (ci.yml is the only workflow).
