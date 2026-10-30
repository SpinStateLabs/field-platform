# C-541: test-quality audit, tests that cannot fail (read-only), Lane 10

Scope: main at the time of writing; every `test_*.py` under the repository (295 files, 4,326 test functions by AST; node `.mjs` harnesses and `/fixtures/` excluded). Tool: 20261103-0300-design-c541-weak-tests-audit.py (AST, `python weak_tests.py <checkout>`), full output: 20261103-0300-design-c541-weak-tests-audit-output.txt. No fix proposed, per the card; file:line below, class only.

VERDICT: the suite is in good shape. No test is vacuous by construction: 0 skips without a reason, 0 `xfail` without a reason, 0 asserts on a mock's own configured return value, 0 `assert x or True`, 0 tests that swallow a failure with a bare `except: pass` around the assertion. Four tests have no assert and rely on an exception, and 18 assert only something weak. Confidence HIGH for the counts (AST), MEDIUM for "weak" (a judgement of the assertion's strength, not of the test's value).

## ASSUMPTIONS
1. "Cannot fail" means: no execution path of the test body can raise, or the only assertion is always true.
2. A helper that asserts (a same-module function called by the test, followed transitively) counts as an assertion.

## Objections first (what this audit cannot see)
1. It is syntactic: a test can have a real-looking `assert` against a value the code under test never influences (a fixture that returns the expected value). Only a mutant run finds that; the builders already run mutants per card, but I did not.
2. Cross-module helpers and fixtures that assert are not followed beyond the module; they are counted as candidates, not as findings (38 of 42 "no assertion" tests resolved to a same-module helper that asserts).
3. Node harnesses (`*.mjs`) were not scanned: out of the AST tool's reach.
4. A test that "cannot fail" today may be a regression guard that only fails after a future change (for example "the discovered file set is not empty"): value without a way to see it fail now.

## Findings
A. No assertion, relies on an exception (4; legitimate shape, risk only if the callee became a no-op):
- packages/field-core/tests/test_rotation_events_r2.py:93 `test_every_frozen_event_validates` and :181 (`re_.validate(...)` must not raise; a validator that accepted everything would pass: the negative cases elsewhere in that file protect it, not read case by case).
- tools/tests/test_renew_token.py:2914 `test_the_tool_parses_on_the_gb10_python` (`ast.parse(..., feature_version=(3, 12))`: a syntax error fails it; sound).
- tools/tests/test_yaml_duplicate_keys.py:96 `test_no_duplicate_mapping_key` (`scan_file` is `load_strict`, which raises on a duplicate key; protected by its own "the checker itself" tests in the same file).
B. Assertion through a helper that asserts, not a finding (38): tools/tests/test_phase_g_check.py (14), test_harness_wait_honoured.py (5), test_operator_cli_c2.py (2), field-core test_operator_auth_format2.py and machine_verifier (8), the sealed-ledger readers, agent-registry atomicity and others. Listed in the output file.
C. Constant or self-equal assertions (14): 11 are `assert False, "expected X"` markers placed after the call in a `try/except X` block (conformance-sentinel test_sentinel.py:180, :188; field-agent test_field_agent.py:50, :63, :79, :139, :158, :169, :179, :191, :279): fine IF the `except` names the specific exception (they do: ActionBlocked, AgentKilled, ...); `pytest.raises` is the modern form (style only). 3 are determinism checks calling the same function twice and comparing (field-core test_key_fingerprint.py:43, sentinel test_scorecard.py:86, tools test_deployment_agent_refuse.py:181): valid, they cannot catch a function that is consistently wrong.
D. Weak-only assertions (18 tests whose every assert is a weak shape; review candidates, value judged by the reader):
- `is not None` only (11): defence-shield test_clauses.py:40, :64; test_detection_pins_c148.py:162, :167, :192, :197; field-core test_clients_resolve_manifest.py:119, :405; test_operator_auth_format2.py:404; tools test_deployment_agent_refuse.py:157; test_renew_token_pins_c212.py:63. Each proves a detector or parser returned something, not what.
- bare truthiness `assert x` (5): defence-shield test_evidence.py:36 (`test_clean_pack_verifies`); tools test_fly_identity_c5.py:485; test_topology_lint.py:893, :1180; test_yaml_duplicate_keys.py:165.
- `isinstance` only (2): force-gateway test_upstream_and_judge_pins_c179.py:139; tools test_deployment_agent_rotation.py:1119.
E. Broad `except Exception: pass` inside a test (1): services/kill-switch/tests/test_heartbeat_store_lazy_init.py:105 is cleanup (`extra.close()`) before the real assertion at :111; benign.
F. Skips: no skip lacks a reason and no `xfail` lacks one.

## Recommendation (not requested as a fix; for the card owner)
A cheap lint to keep this true: the AST tool above as a test (`tools/tests`), failing on categories "skip/xfail without a reason", "assert <constant>" outside the `assert False, "expected"` idiom, and "no assertion and no resolvable helper" with the four in A allowlisted by name. Category D is a judgement list for a human, not a gate.

## What I did NOT do
Did not run any mutant. Did not scan `.mjs` harnesses or non-`test_*.py` names (e.g. `*_test.py` matched none of significance). Did not read category D tests to judge each one's value. Did not edit any file.
