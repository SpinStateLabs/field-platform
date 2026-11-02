# reviewer Lane 15: C-1119, post-landing seam audit of cb19 on main b58262000c73e0df802f24693b382d438ce0a205

VERDICT: PARTIAL, UNVERIFIED for the 16-suite set (local run, no GX10). One finding measured; the suite run is not finished. Main re-read with git ls-remote at report time: b58262000c73e0df802f24693b382d438ce0a205 (unmoved). Read-only on main and on every PR; nothing pushed except this note.

## OBJECTIONS FIRST (what is wrong or unmeasured in this report)
1. The per-service suites are NOT all done (see "Run"). A pass here proves nothing about the groups still running.
2. My first run used a PYTHONPATH with ":" separators, which native Windows Python ignores, so it imported field-core from an older checkout. Those results are discarded. The corrected run uses ";" and I checked that field_core and delegation_authority resolve to the audited worktree.
3. The lifecycle-manager step of the corrected run uses absolute PYTHONPATH entries (a deviation from "relative"); the other groups use relative ones.

## FINDINGS
- F-C1119-1 MEDIUM-LOW (MEASURED): `services/delegation-authority/src/delegation_authority/cli.py:152-163` keeps its own `GuardedOperatorAuth` with no same-origin check (`auth_flow` at :160 tests only `is_guarded`). `packages/field-core/src/field_core/guarded_operator.py:99-108` (`_same_origin`, C-731 F-C731-1) and `services/lifecycle-manager/src/lifecycle_manager/cli.py:168-176` give another origin no pair. Probe (placeholder pair values, no network): one guarded POST path, base origin A and a second origin B. delegation CLI copy: pair on A, pair on B. field-core copy: pair on A, no pair on B. Mitigation seen, not a fix: the CLI client sets `follow_redirects=False` (:177-178) and builds its requests from its own base. I do NOT know whether any call site passes a foreign URL, so reachability today is unproven. The cb19 commit message for the CLI says "this module keeps its own copy of the guard", which is the drift the C-511 work removed elsewhere.
- F-C1119-2 LOW (READ, not run): `tools/provision_ssl_agents.py:202-226` has the same shape (its own `_GuardedOperatorAuth`, no origin check, no base in the constructor). It is an operator tool, not a service; the same question about foreign URLs applies.
- Checked and clean by reading: `services/kill-switch/src/kill_switch/cli.py:132` subclasses the field-core class (inherits the origin check).

## SEAMS CHECKED, NO PROBLEM FOUND
- Proxy lint and ADR 10 symbol pins on the merged tree: `tools/tests/test_http_env_proxy_lint_c57.py`, `test_adr10_note_symbols_c1026.py` plus the environment/anchor tests found by name: 166 passed (185 s), after the path fix.
- field-core suite on main: 1540 passed, 2 skipped, 1 warning (259 s).

## RUN
Corrected run, relative PYTHONPATH, PYTHONUTF8=1, no stdin. Done: tools lints 166 passed; field-core 1540 passed 2 skipped. In progress when this note was written: sealed-ledger (about 60 percent). NOT run: agent-registry, delegation-authority, kill-switch, lifecycle-manager (queued behind it). I will post a one-line follow-up with their counts when they finish, or say so if they fail.
Not done: no mutants (the finding needed a probe, not a mutant), no comparison of ma3/cb17/ma2e file overlap beyond reading cb19's 25 changed files.

## ASK
Builder card (coordinator to number): give the delegation CLI guard the origin check (or make it subclass the field-core class as kill-switch does) with a test that another origin gets no pair, and say in the PR whether `tools/provision_ssl_agents.py` is in scope. Reviewer delta needed after.
