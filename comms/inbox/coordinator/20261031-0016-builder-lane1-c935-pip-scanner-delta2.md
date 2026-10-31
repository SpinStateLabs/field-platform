# Builder Lane 1: C-935 conditions on PR 343 (capped round)

Head e531734 on test/ci-pin-test-every-workflow-c460 (on 30015c3; fast-forward). Identity Don Hagell set in the worktree before committing. File: tools/tests/test_ci_pip_pins_c23.py only.

F-C935-1 CLOSED: statements_sep keeps separators; a define arms $C only as a standalone statement (before-separator newline, `;` or `&`; after-separator newline or `;`). `false &&`, `[[ ]] &&`, `||`, trailing `&`, pipeline-element and `&&`-left defines do not arm; a trap naming C disarms for good. 13+ pinned cases, accepted cases (`;`, blank lines, `sleep 1 &` before the define).
F-C935-2 CLOSED: shell: allowlist bash/sh/pwsh/powershell/cmd on job steps, composite-action steps, job and workflow defaults (python, pypy, paths, expressions refused).
F-C935-4 CLOSED: download/wheel/config branch, both half-quoted inline forms, brace group each have a case that fails when the rule is removed. 29 mutants of the new rules killed (3 survivors got cases).
F-C935-3, -5: listed in the header as documented limits (runtime-built names, alias/hash/PATH, unnamed pip config, sourced files, `-c /dev/stdin`, fail-closed false positives); not chased.
HEADER now ends with a statement of scope: text scan, not a shell; does not prove no unconstrained install can run; further spellings out of scope.
PR body corrected: the C-730 "all killed" claim was wrong (M37 survived); equivalents named.
EVIDENCE: 193 tests in the file pass. Whole tools suite via /workspace/resumable-suite.sh with /workspace/venv-c730 (clean, per ci.yml): files ok=53 of 53, EXIT=0, verified before the push. NOT run: GX10 suite, CI on this head.
RECOMMENDATION: declare the pip-pin scanner class DONE at this round. Five reviews (C-450, C-627, C-730, C-935 and this card) each found new spellings of the same class; ci.yml passes and is unchanged; the residual limits are listed in the test header. Any further spelling should be caught by workflow-diff review, not by widening this text scan. Merge as a strict tightening.
