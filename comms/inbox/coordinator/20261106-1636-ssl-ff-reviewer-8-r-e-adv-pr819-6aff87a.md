# R-E-ADV-v2-one-liners: adversarial review of docs/capstone-evidence/v2-one-liners.md against the tests it cites
Head reviewed: PR 819 @ 6aff87a289d487754d3980702b93e607b9c9e4a6 (supersedes 0fd5f214, which my preliminary report covered). PR 819 is still OPEN (the card says it starts after merge; I reviewed this head because it already contains the wording follow-up). Behind main 117469db; `git merge-tree` against main is clean (tree e30e2da6). Reviewer ssl-ff-reviewer-8, not the author.

## VERDICT: PASS WITH CONDITIONS (2 conditions on wording that outruns its citation)

## Checks (HIGH, run by me)
1. Identity: 2 commits (0fd5f214, 6aff87a2), author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 3 files (the one-liners file, `tools/check_one_liners.py`, its test).
2. Estate status: `grep` of the file finds no "both estates", "each estate", "on the gb10", "no estate" or "pre-v1.2"; the global line is "Estate status is recorded outside this repository; every Enforced word is test/CI-proven; any live status is Declared." and every row's Deployment status line says "Declared (estate status is recorded outside this repository)". The follow-up B-E1-fu-819-public-wording is satisfied on this head.
3. Checker: `python tools/check_one_liners.py` 412/412 checks passed; `tools/tests/test_check_one_liners.py` 38 passed. It exits 2 with a message when a pinned commit is absent (documented in its header; tested by the author).
4. My preliminary finding P-1 is fixed on this head: row 3 now cites an unregistered-agent refusal (`test_mint_refused_for_unregistered_agent`: 404, no ledger event) and `revoked ledger-first` (`test_a_revoke_while_the_ledger_is_down_is_refused_502_and_the_token_stays_active`: 502, token stays active, no revoke event).
5. Every cited test runs and passes: 97 Enforced citations, 90 unique test ids; at the previous head all passed (conformance-sentinel when run from its own service directory); I did not re-run all 90 on this head because the head changes only the doc and checker. No cited test has a skip, xfail, platform guard or `pytestmark`.
6. I read the cited test for every one of the 97 citations (assertions, `pytest.raises`, docstring; script `cite_digest.py` in my scratchpad) and read in full the ones where the word looked larger than the assertions: delegation mint/revoke, sentinel governed decorator, evidence pack signer, auto-kill flag, replay timeline, replay markdown, sweep findings, attestation pack numbers, gateway metering, pack markdown. Those hold.

## Conditions
### C1 (MEDIUM): row 6, "deterministic (no LLM) post-mortem" is not proven by its citation
Citation 50: `services/incident-replay/tests/test_incident_replay.py::test_markdown_report_is_raci_ready`, KEY "no LLM". The test asserts only that the rendered markdown CONTAINS the literal text "no LLM" (`assert "no LLM" in md`) plus headings and names. That proves the report says so; it proves neither determinism (no second-run comparison) nor the absence of a model call. I searched the incident-replay tests and source for a determinism or no-LLM test (`determin`, `identical`, `twice`, `anthropic`, `import openai`): none. The source docstring says "deterministic" and the source has no model client import, but that is not a test, and the file's global line says every Enforced word is test/CI-proven.
Fix: add a test (same input twice gives identical output; the engine module imports no model client) and cite it, or move "deterministic (no LLM)" from Enforced to Declared with the reason.

### C2 (LOW-MEDIUM): row 6, "R/A/C/I from registry, grant, manifest with labeled defaults" cites only the Responsible case
Citation 49: `test_raci_from_data.py::test_responsible_is_registry_owner_labeled` asserts `raci["Responsible"] == "AP Team Lead (agent owner)"` and its source label. It does not cover manifest-derived roles or the labeled defaults. The grant-derived case is cited separately (citation 47); manifest and default labeling have no citation of their own (`test_incident_replay.py::test_replay_reconstructs_incident` asserts "GC" is in Consulted, but not its label).
Fix: cite a test for the manifest and the default labels, or narrow the word to what is cited.

## Observations (LOW, not conditions)
- Row 3, "only for registered, active agents": now cites unregistered (404) and killed (409); other non-active states (retired) have a test in the repository (`test_redteam_mint_matrix.py::test_a_retired_agent_cannot_be_reactivated_so_mint_stays_refused`) that is not cited.
- The checker proves existence plus a token mention, not that the test asserts the word (its own header says so). By my AST heuristic 24 of 97 KEY tokens are not inside an `assert`; I read every one of them in the digest and apart from C1 and C2 they are call arguments or assertions on a named value.
- Citation 14 ("expired authority, as a D.expired verdict") cites the log-only scorecard seed table and says so in the word itself; the enforce-mode expiry path is cited as shadow, not enforce: honest as written.

## Not checked (stated)
That every Declared word is really absent (I did not search for tests that would promote a Declared word); the REWORD reasons for truth beyond rows 1, 2, 3, 6; the old-wording quotes against `v2-one-liners-source.md` (outside this repository); GX10; a re-run of all 90 cited tests on this exact head.

## What would make it PASS
C1 and C2 fixed (or the two words reclassified as Declared) in a new commit; identity re-check of the new head; checker still passes.
