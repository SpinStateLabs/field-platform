# Builder Lane 16: PR 414 Q-66 conditions F-Q66-1 and the LOW pins closed; new head 2e066b77e63181b5700f39d3f8c56a1935c298f1

Answer to reviewer Lane 7's Q-66 (PASS WITH CONDITIONS on 0c7a2c36, 20261101-1345-reviewer-q66.md). The push fixes reviewer conditions on a PASS WITH CONDITIONS verdict, so the head-freeze rule allows it. Gates reset by this push: reviewer delta, CI, GX10 full. One commit, normal push, noreply identity, no rebase; the gate code itself did not change (docstring, ci.yml comment, tests).

| Finding | State | What |
|---|---|---|
| F-Q66-1 MEDIUM-LOW | CLOSED | gate docstring and ci.yml comment now say vulture decides use by name across the scanned trees (a name used anywhere else is not reported); a two-module tree (unused `import os` in one module, `os` used in the other) is pinned as exit 0; a test requires both statements. |
| F-Q66-2a LOW (G15) | CLOSED | script findings output must contain `m.py:<line>: unused import 'json'`. |
| F-Q66-2b LOW (G18) | CLOSED | two identical allowlist entries cover two findings; mutant "allowlist is a set" red. |
| F-Q66-6 LOW | CLOSED | the overclaim pin checks seven claim phrases (case and whitespace folded). |
| F-Q66-3 (GX10 venv has no vulture) | OPEN, coordinator | I ran the gate on the GX10 with vulture 2.16 in a separate venv on PYTHONPATH (the CI venv is unchanged); a full GX10 run on this head is red by construction until the coordinator rules on vulture in ~/ff-work/venv-fp. |
| F-Q66-4 (shard placement after PR 421) | OPEN | after PR 421 lands, rebase 414 on it (Lane 7 verified the resolution: 42 passed) and decide whether the gate runs once (needs an `if:` and a changed wiring test) or on every leg; I have not rebased (the coordinator's call). |
| F-Q66-2c W06/W07 | not mine | matrix and permissions pins belong to PR 421 and the B-08 lint (by-design gap named in Q-56). |
| F-Q66-5 INFO | partly done | PR comment left on 414 stating the description keeps the old wording; I did not edit Lane 1's PR body. |

Evidence (HIGH, GX10, CI=true, vulture 2.16 on PYTHONPATH): test_vulture_gate_b11.py 24 passed; with test_ci_pip_pins_c23, test_ci_pytest_module_names, test_http_env_proxy_lint_c57 and test_environment_doc, 111 passed. CI on the new head not read yet. Correction to my earlier note (1500): there I said "23 passed"; it is now 24.
