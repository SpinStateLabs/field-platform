# Builder Lane 1: C-730 conditions on PR 343 (P1-P5)

Head 30015c3 on test/ci-pin-test-every-workflow-c460 (on 1f93620; fast-forward). Identity Don Hagell set in the worktree before committing. Files: tools/tests/test_ci_pip_pins_c23.py, tools/tests/test_yaml_duplicate_keys.py (glob only).

P1 CLOSED: `;`, `|`, single `&`, `)#`, backslash-in-dq, `--constraint`, composite env each pinned with a case that fails if the rule is removed.
P2 CLOSED: `$C`/inline constraints only outside quotes; define arms only before a compound statement/heredoc; C[0]=, printf -v C, mapfile disarm; empty quoted files refused.
P3 CLOSED: PIP_*/UV_* named anywhere in a script or env (any case, container env, non-mapping env); long-option prefixes refused.
P4 CLOSED or NAMED: -mpip, ${PIP:-pip}, variable verb, xargs pip, <(...), expression in command position, function named pip, poetry/pipenv/pdm/conda/mamba/easy_install/pip-sync/uvx/ensurepip, pipx run, uv run --with, uv tool, python -m build, python shell (step/job/workflow) refused. NAMED as unproven in the header: subprocess/python -c installs, scripts, other-repo actions, reusable workflows, container images, `$P` variable-named commands, `eval "$X"`, wrapper functions beyond the pip() form.
P5 CLOSED: dup-key lint globs .github/actions (2 discovery cases, mutant killed); header says `$C` proves flags, not coverage.
EVIDENCE: 163 tests in the file pass; 49 checker mutants killed (3 reworked). Whole `pytest tools` in a clean venv built per ci.yml (/workspace/venv-c730): 3276 passed, 6 skipped, exit 0. NOT run: GX10 suite, CI on this head.
CONFIDENCE: HIGH for pinned cases; MEDIUM that shell parsing is complete (documented limits).
