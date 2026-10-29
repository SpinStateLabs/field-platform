# C-284 reviewer report (Lane 5), part 1 of 2: PR 140 fix/ops-console-symlink-loop-c269 @14a83c0655f16ce54a5b4dca0db8f70f8dbbed94 (C-239 F-C239-1)

VERDICT: PASS on the exact head 14a83c0655f16ce54a5b4dca0db8f70f8dbbed94. A symlink loop anywhere in a manifest ref or in the configured manifest directory now answers a 404 refusal and no longer a 500; the two changed lines are each pinned by a mutant, and no loop detail reaches the body. Full gx10_verify is green. PR 143 (the second half of C-284) is in its own report. Class and file:line only; no values.

OBJECTIONS FIRST
1. The fix catches `RuntimeError` at two places (api.py:204 and :216). On Python 3.12 a loop makes `Path.resolve(strict=True)` raise `RuntimeError`; on a newer Python the same input is, to my recollection, an `OSError`, which the old code already caught (training data, MEDIUM; I did not test another Python). The comment on both lines names the 3.12 case. A third place that resolves a path would need the same catch; I grepped api.py for `resolve(`, `is_file()` and `stat()`: the three `resolve` calls (:203, :213, :215) sit inside the two guarded `try` blocks, and `is_file()` and `stat()` (:220, :222) run on the already-resolved path. The only caller is api.py:521. [HIGH, run and read]
2. The refusal is 404 ("no manifest file at that ref"), the same answer as a missing file. A caller cannot tell a loop from absence; that is the intent (nothing about the directory layout is disclosed). [HIGH]
3. The catch is not minimal in the sense that nothing pins it to `RuntimeError` alone: the mutant that widens it to `Exception` survives (item 4). LOW. [HIGH, run]

ASSUMPTIONS
1. Base f75baab (merge-base equals main); one commit; author and committer Don Hagell noreply; changed files: services/ops-console/src/ops_console/api.py (+2 -2) and the new services/ops-console/tests/test_manifest_loop_c269.py (+125). [HIGH]

REASONING
1. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr140, base f75baab): core_services 2229 passed 4 skipped; tools 1976 passed 3 skipped; agent-registry 259; sentinel 111; incident-replay 91; crosswalk 162 (1 skipped); gateway 210; lifecycle 185; attestation 66; ops-console 214 (207 plus 7 new); claude-approver 101; field-agent 118; topology_lint OK; EXTRA defence-shield 113. VERDICT CI-EQUIVALENT STEPS GREEN. [HIGH, run]
2. My own probes on the unmutated head (through the route, with a temporary manifest directory containing a good file): a self-referencing link, a two-link cycle, a directory-loop component in the middle of the ref, a ref that goes through `..` past a loop, and a manifest directory that is itself a loop: every one answers 404 with the body `{"detail": {"agent_id", "ref", "validation": "missing", "reason"}}`; the reason is the fixed text, no path, no exception name, no "loop" or "too many levels" wording. A good file in the same directory answers 200. [HIGH, run]
3. Mutants on api.py 195-225 and 379-388, new file alone: 25 (4 hand): 11 killed. The two changed lines: removing `RuntimeError` from the first catch (the directory) KILLED; removing it from the second (the ref) KILLED; a loop answered 403 instead of 404 KILLED. [HIGH, run]
4. The survivors (14), by class: the "catch broad `Exception`" widening (hand; LOW, item 3 of objections); constants and flips on pre-existing lines that this PR did not touch (:198, :200, :207, :209, :213, :220, :222: the not-configured, containment, suffix and size answers), which the ops-console suite and the PR 143 file pin; I did not rerun those survivors against the whole suite for this card. [HIGH on the list, MEDIUM that the rest of the suite kills them]
5. Public-repo hygiene: the test file builds its links in a temporary directory; no address, flag value or secret. [HIGH]

CONCLUSION
PASS on 14a83c0. Optional LOW card (coordinator numbers it): P1 builder, services/ops-console/tests/test_manifest_loop_c269.py: one case that asserts a non-loop `RuntimeError` is not swallowed (kills the widening to `Exception`); done when that mutant dies.

What I did NOT do: run PR 140 together with PR 143; test on a Python other than the GX10's 3.12; rerun the 14 survivors against the whole ops-console suite.
