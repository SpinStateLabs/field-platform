# C-303 reviewer report (Lane 5): PR 157 test/duplicate-key-lint-gaps-c294-r2 @c39197a7f17934d3176329463411af84aef4000c (C-294; my Lane 4 colleague's C-291 findings)

VERDICT: PASS on the exact head c39197a7f17934d3176329463411af84aef4000c. The three original surviving mutants (scan body replaced by `pass`; case-insensitive compare; compare as strings) are red; the per-file injection runs on every discovered file and cannot pass on an empty file set (the suite fails, it does not skip); two more mutants I added on the new merge-key rule and on discovery are red. Full gx10_verify is green. Class and file:line only; no values.

OBJECTIONS FIRST
1. Not "tests only" in effect: the checker lives in the test file (`_construct_mapping`), and the PR changes it: a second `<<` merge key in one mapping is now refused (tools/tests/test_yaml_duplicate_keys.py:33-40). That is stricter than before; every discovered workflow and compose file still loads (the per-file test is green in the full run), so nothing in the repository trips it. [HIGH, run]
2. The type rule is only pinned for one pair: `1` and `'1'` are not duplicates (the new test), but the checker treats `1` and `true`, and `1` and `1.0`, as duplicates (Python equality: probed on the head: all three refused as "duplicate key"). YAML itself distinguishes them, so this is a false positive in the checker, not in any file here (`on` and `true` are the same boolean in YAML 1.1, so that pair is a true duplicate). LOW. [HIGH, run]
3. The branch is one commit on a946d26 (main is f7263fd; I judged the head as it is); author and committer Don Hagell noreply; one file, tools/tests/test_yaml_duplicate_keys.py (+57 -5). [HIGH]

ASSUMPTIONS
1. Verify base a946d26; the three original mutants are those named in the card. [HIGH]

REASONING
1. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr157, base a946d26): core_services 2244 passed 4 skipped; tools 2090 passed 3 skipped; agent-registry 277; sentinel 111; incident-replay 91; crosswalk 162 (1 skipped); gateway 257; lifecycle 212; attestation 66; ops-console 222; claude-approver 162; field-agent 150; topology_lint OK; EXTRA defence-shield 166. VERDICT CI-EQUIVALENT STEPS GREEN. [HIGH, run]
2. The original survivors, rerun on this head (mutants on test_yaml_duplicate_keys.py 28-82; my runner with bytecode caching off): `scan_file` body returning None (the old "body replaced by pass"): KILLED; the duplicate test made case-insensitive: KILLED; keys compared as strings: KILLED; the duplicate check removed: KILLED. [HIGH, run]
3. Not vacuous: `_files` returning an empty list (which makes the parametrised tests skip): KILLED, by `test_the_scan_sees_the_workflow_and_the_compose_files` (it asserts the GB10 compose file is discovered), so the suite fails instead of skipping. The injection itself: the key chosen is the first top-level key of the real file; replacing it by a name that cannot repeat, or injecting nothing, turns the per-file tests red (3 of 3 KILLED). Dropping the `compose*.yaml` discovery pattern survives (no file matches it today; LOW, the nested-directory test covers one pattern only). [HIGH, run]
4. The new rules: the second merge key mutants (limit raised to 2, merges never counted, the raise removed): all KILLED; `<<: [*x, *y]` (a merge list) is still accepted (test passes). Generated mutants (25 sampled): 23 killed of the 28 in total with the hand set; survivors: the line number in the error text (:48, equivalent) and `isinstance(node, SequenceNode)` forced True in the tagged-value constructor (:57, pre-existing path, no test has a tagged scalar; LOW). [HIGH, run]
5. Public-repo hygiene: test code only. [HIGH]

CONCLUSION
PASS on c39197a. Optional LOW cards (coordinator numbers them): P1 builder, tools/tests/test_yaml_duplicate_keys.py: use a type-aware key (for example `(type(key), key)`) so `1` and `true`, `1` and `1.0` are not reported, plus a test; P2 builder: a case for `compose*.yaml` discovery.

What I did NOT do: run the CI job itself; test with a different PyYAML version than the GX10's.
