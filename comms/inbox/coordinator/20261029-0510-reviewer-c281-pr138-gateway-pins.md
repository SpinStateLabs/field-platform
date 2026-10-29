# C-281 reviewer report (Lane 5): PR 138 test/force-gateway-pins-c179 @a8209e105005f8f6a1a0f7e4f1baf3565681695c (C-170 F-C170-2/-3)

VERDICT: PASS on the exact head a8209e105005f8f6a1a0f7e4f1baf3565681695c. Every hand mutant I wrote for the upstream non-200 passthrough and the hygiene judge's key and status guards is killed, and the generated mutants that survive the new file are all killed or sit on lines outside F-C170-2/-3. Full gx10_verify is green. Class and file:line only; no values.

OBJECTIONS FIRST
1. Pins say what the code does today: the upstream non-200 answer is passed through unchanged and a judge answer with status 400 or above is a judge failure; the tests now fix both. I think both are right; they are decisions the tests record. [HIGH]
2. My generated mutants are mechanical and sampled (64); an argument swap or call removal is outside the generator. [HIGH]
3. Eight survivors remain on lines this PR did not add (item 4); none is in F-C170-2/-3. [HIGH]

ASSUMPTIONS
1. Base f75baab (merge-base confirmed equal to main for this card); one commit; author and committer Don Hagell noreply; one new file services/force-gateway/tests/test_upstream_and_judge_pins_c179.py (+157, 47 cases). [HIGH]

REASONING
1. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr138, base f75baab): core_services 2229 passed 4 skipped; tools 1976 passed 3 skipped; agent-registry 259; sentinel 111; incident-replay 91; crosswalk 162 (1 skipped); force-gateway 257 (210 plus 47); lifecycle 185; attestation 66; ops-console 207; claude-approver 101; field-agent 118; topology_lint OK; EXTRA defence-shield 113. VERDICT CI-EQUIVALENT STEPS GREEN. The new file alone: 47 passed. [HIGH, run]
2. Mutants (regions: force_gateway/api.py 885-945 and 190-205, hygiene_judge.py 110-175; seed in my config; 4 hand plus 60 generated = 64): the new file alone kills 43; rerunning the 21 survivors against the whole gateway suite kills 13 more; 8 survive. [HIGH, run]
3. Hand mutants, all killed by the new file: the upstream status test `!= 200` widened to `>= 400` (so a 3xx or 2xx non-200 answer would change); the judge status guard widened to `>= 400`; the judge status guard removed; the judge key guard removed. [HIGH, run]
4. The 8 survivors, all pre-existing lines outside the findings: api.py:899 (`and`/`if` forced in the governor-usage condition: both flip a path where no governor or no agent id is present; no test sends usage with those absent), api.py:903 and :904 (the default 0 of a missing token count to 1), api.py:934 (the latency arithmetic: `* 1000`, the subtraction and the constant; latency is a reported number no test pins). Proposed as one LOW builder card below. [HIGH, run]
5. Public-repo hygiene: test constants only; no address, flag value or secret. [HIGH]

CONCLUSION
PASS on a8209e1. Proposed card (coordinator numbers it): P1 builder LOW, services/force-gateway/src/force_gateway/api.py:899, :903-904, :934 and services/force-gateway/tests: pin the governor-usage condition (no governor, no agent id), the missing-token default and the reported latency unit; done when the 8 survivors are killed or justified.

What I did NOT do: mutate the rest of the gateway; run against a real upstream or judge; read the hygiene judge outside lines 110-175.
