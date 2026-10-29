# C-320 reviewer report (Lane 5): PR 171 C-285 r3 @bedb667de6e71b33e0f9b916c106d12187b32e63 (re-review of my C-313 FAIL on PR 163 @521b2e6)

VERDICT: PASS on the exact head bedb667de6e71b33e0f9b916c106d12187b32e63. The regression is fixed (the provisioning test now supplies the estate base URL itself and the whole tools suite is green with the variable unset), the two skills name the requirement, and the history line no longer reads as if the old pin were current. Full gx10_verify is green. Class and file:line only; no values.

OBJECTIONS FIRST
1. Which branch: no builder report for this card is in `comms` yet, so I judged PR 171 as the coordinator said. PR 163 moved to 5dd47ea (two commits on a946d26: the original change plus the test fix, without the SKILL.md and runbook edits); PR 171 is three commits on main 3bbc9d3 (the same change, the test fix, then C-318's docs) and is the superset. I did not review 5dd47ea separately. Main has since moved again (516ca76). [HIGH]
2. Three commits (dea240b, 2128b63, bedb667), not one; author and committer of all three Don Hagell noreply; the coordinator batches. [HIGH]
3. The fix to the old test is `monkeypatch.setattr(mod, "PROXY", rec.base)` (tools/tests/test_operator_cli_c2.py:803): it sets the module attribute, not the environment, so the test no longer depends on the process environment; any other test that calls `provision_ssl_agents.main` without the variable would still fail the same way. The full run (variable unset) shows no other tools test failing; I did not separately enumerate callers of `main`. [HIGH, run]
4. The C-267 done-when ("no value outside tests") is still open at the four live-manifest lines (manifests/ssl-invoicing-agent.yaml:43 and :80, manifests/ssl-timekeeping-agent.yaml:47 and :86); the PR does not claim otherwise. [HIGH, run]

ASSUMPTIONS
1. Verify base 3bbc9d3 (the PR's merge-base). The PowerShell test is skipped on the GX10 (4 skipped in tools); I ran the shim itself on Windows PowerShell 5.1 in C-313 (same bytes: sha256 prefix 27472c77 at this head). [HIGH]

REASONING
1. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr171, base 3bbc9d3, `FIELD_PROXY_URL` not set in the run): core_services 2244 passed 4 skipped; tools 2104 passed 4 skipped; agent-registry 277; sentinel 111; incident-replay 91; crosswalk 162 (1 skipped); gateway 257; lifecycle 212; attestation 85; ops-console 222; claude-approver 162; field-agent 150; topology_lint OK; EXTRA defence-shield 166. VERDICT CI-EQUIVALENT STEPS GREEN. The test that failed on 521b2e6 (`test_provision_ssl_agents_main_hands_the_flag_pair_to_the_engine_client`) is inside the tools step and passes. [HIGH, run]
2. P2 (skills): agents/ssl-invoicing-agent/SKILL.md and agents/ssl-timekeeping-agent/SKILL.md each gain one paragraph: `FIELD_PROXY_URL` must be set (no default); `field-rest.ps1` throws at load when unset, and so does `tools/ssl-verify-token.ps1`, which dot-sources it. That matches the behaviour I verified in C-313 and the dot-source in tools/ssl-verify-token.ps1. [HIGH, read]
3. P3 (history line): docs/runbooks/token-renewal.md:1203 now says `412d1352…` is "a historical value: §5.2 now pins the C-285 bytes"; line 931 still pins `27472c77745bef7f1eb785ae7f52a0dd5e34e03f2d2b693052da0ed3ae7b7a49`, which equals the sha256 of tools/field-rest.ps1 at this head. [HIGH, run]
4. Everything else in the PR is as reviewed in C-313 (guard, exit 2, the sketch manifest's reserved name, the new test file's six cases, the mutant results); I did not rerun the mutants on this head: the source files changed since that review are none (the three new commits touch one test line and three docs). [HIGH on the diff between heads: `git diff pr163b pr171` shows only the two SKILL.md files, token-renewal.md, and unrelated main changes]
5. Scan on the head with the estate value in a variable: non-test lines holding it: 4 (the live manifests); no other private-range value appears outside tests. [HIGH, run]
6. Public-repo hygiene: wording and one test line only. [HIGH]

CONCLUSION
PASS on bedb667. C-313 P1, P2 and P3 closed; P4 (the four live-manifest lines, C-267) remains. No new cards.

What I did NOT do: review PR 163's new head 5dd47ea on its own; rerun the mutants on this head; run the PowerShell test in CI.
