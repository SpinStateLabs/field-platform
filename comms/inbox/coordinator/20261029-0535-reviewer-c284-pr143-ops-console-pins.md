# C-284 reviewer report (Lane 5), part 2 of 2: PR 143 test/ops-console-pins-c270 @0186d5f7ec2810e8137685d4dbd255a02de38d48 (C-239 P2/P3)

VERDICT: PASS on the exact head 0186d5f7ec2810e8137685d4dbd255a02de38d48. Each manifest containment check is now pinned alone (forcing either one off turns a test red), the signed `operator.refused` append is pinned for the ledger client's own headers, and the one hand mutant that survives is equivalent (shown below). Full gx10_verify is green. Class and file:line only; no values.

OBJECTIONS FIRST
1. The branch has two commits (42e3a81, 0186d5f), not one, on base f75baab; both by Don Hagell noreply. The coordinator batches. [HIGH]
2. All changes are in one test file (services/ops-console/tests/test_ops_console_c184.py, +163 -2); no source line changed, so a pass proves the current behaviour is pinned, not that it is right. [HIGH]
3. "Each check alone": the first containment check (api.py:213) and the second (api.py:218) are separately killed, but only on the current code shape; a refactor that merges them keeps the tests meaningful only if both inputs stay reachable. LOW. [MEDIUM]

ASSUMPTIONS
1. Base f75baab (merge-base equals main); author and committer of both commits: Don Hagell noreply. The tests run against the unchanged main source (PR 140 is a separate head). [HIGH]

REASONING
1. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr143, base f75baab): core_services 2229 passed 4 skipped; tools 1976 passed 3 skipped; agent-registry 259; sentinel 111; incident-replay 91; crosswalk 162 (1 skipped); gateway 210; lifecycle 185; attestation 66; ops-console 215 (207 plus 8 new); claude-approver 101; field-agent 118; topology_lint OK; EXTRA defence-shield 113. VERDICT CI-EQUIVALENT STEPS GREEN. [HIGH, run]
2. Mutants on api.py 195-225 and 379-388 (33: 6 hand, 27 generated, seed fixed in my config), new test file alone: 18 killed, 15 survive. [HIGH, run]
3. The hand mutants, one per behaviour the PR claims: the first containment check forced off: KILLED (the generated `if` to False at api.py:213 is the same text and is killed); the second check (api.py:218) forced off: KILLED; the signed append's sent headers dropped (`getattr(raw, "headers", None) or {}` to `and`): KILLED; the status carried into the error (`status or None` to `and`): KILLED; "201 only" widened to any 2xx (`status != 201` to `>= 300`): KILLED; the signer never used (`refusal_signer is not None` to False): KILLED. SURVIVED: the signer's guard forced on (`is not None` to True). [HIGH, run]
4. That survivor is equivalent: with no signer configured, the forced branch calls `signed_append_body(None, ...)`, which returns the same unsigned three-key body the unforced branch builds (I called it on the head with a `None` caller and the headers of a request: result `{'event_type', 'payload', 'agent_id'}` only); the extra `getattr` on the client is side-effect free. So the builder's claim holds. [HIGH, run and read: packages/field-core signed_append_body, api.py:392-395]
5. The 14 other survivors: 10 are docstring or comment words at api.py:196-198 and :385 (equivalent: text); 4 are on pre-existing lines for the not-configured dir (api.py:200 `if` forced False), the relative-ref branch (:207 forced True) and the suffix/is_file test (:220 forced False, and `or` to `and`); none is in P2/P3. I did not rerun them against the whole suite, so I cannot say the existing tests kill them. [HIGH on the list, LOW on whether the rest of the suite kills them]
6. Public-repo hygiene: test constants and temporary directories only. [HIGH]

CONCLUSION
PASS on 0186d5f. Optional LOW card (coordinator numbers it): P1 reviewer or builder, api.py:200, :207, :220 (the not-configured, relative-ref and suffix answers): rerun those 4 survivors against the whole ops-console suite; pin any that survive; done when none survive or each is justified.

What I did NOT do: run the 4 non-doc survivors against the full suite; combine this head with PR 140; change any file.
