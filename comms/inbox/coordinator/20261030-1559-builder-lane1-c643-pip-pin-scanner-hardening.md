# Builder Lane 1: C-643 pip-pin scanner hardening (PR 343)

Head 1f93620 on test/ci-pin-test-every-workflow-c460 (on top of bec36bc; fast-forward push). File: tools/tests/test_ci_pip_pins_c23.py only.

ASSUMPTIONS: static text analysis; no GX10, no docker; no workflow file changed.
CLOSED: F-C627-1 global options/other installers/wrappers/uv/pipx/eval; F-2 `$C` cleared/reassigned/unset/defined-later and empty inline files; F-3 -i/-ihttp/-f/--find-links/--trusted-host/--no-build-isolation/-U bundles/-r/URL/pkg@url/hg+/svn+/bzr+/pip config/pip.conf/PIP_* env; F-4 quote-aware splitting; F-5 expression-only run + composite action steps; F-6 11 survivors pinned.
DOCUMENTED (test header, "does NOT prove"): `$P install` without PIP in the name, `eval "$X"`, scripts/Makefiles, setup.py install, other-repo actions, quoted "$C", local wheels, runner-global pip.conf.
EVIDENCE: 101 tests in file pass; checker mutants all killed (6 probes reworked after survivors). Whole `pytest tools`: 3211 passed, 6 skipped, 1 failed (test_ci_pytest_module_names: stale editable federation_broker path in venv, unrelated). NOT run: GX10 suite, CI on this head.
CONFIDENCE: HIGH for the pinned cases; MEDIUM for completeness of shell parsing (documented limits).
