# Reviewer report: PR 340 @ 25ffdc11022c6b8ae655fef5d3b4548499aebe3a (C-577, reviewer C-536 / C-621: docs/INTEGRATION.md)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Docs only: docs/INTEGRATION.md (+37/-13), 4 commits on base 5808a5cd. Author and committer of all 4 = Don Hagell 13129187+dhagell@users.noreply.github.com, trailers Sonnet 5.5 (HIGH). `git merge-tree --write-tree origin/main pr340` clean (HIGH). Light run, docs only. No estate address, flag value, build id or deploy status added; the PR removes estate-deploy statements ("Both estates run pre-v1.2 images ...", "placing it on the estates is Don's step") and a personal-name example roster entry.

## Objections first
1. The page now states line-number citations (`mode.py:34-47`, `doa.py:40`, `api.py:196-202`, `:358-375`, `:551-585`, `:887-910`, `:24-40`, `:41-43`); line numbers drift. The PR adds a banner saying they were read against 5808a5c (2026-10-30) and must be re-checked, which is the honest statement; it is still a maintenance trap (see F-C577-2).
2. The new gateway-enforce paragraph is dense and restates `services/force-gateway/README.md`; two copies of one contract can diverge. It points to the README for the full contract.
3. No test pins any of the new claims (see mutants).

## Verified against the code (head tree equals the base tree for code; the cited files are identical on current main for these lines)
- Sentinel mode: mode.py:34-47 resolves `FIELD_SENTINEL_MODE` case-insensitively with `-` read as `_`; log_only, logonly, enforce, enforcing, enforced; blank or unset = log-only; anything else raises `InvalidSentinelMode`, and conformance_sentinel/cli.py:210-214 turns that into "one line, exit 2, nothing bound": "refuse to start" is true (HIGH).
- doa.py:40 is `ROSTER_ENV = "FIELD_DOA_ROSTER"` (HIGH).
- Gateway: the 502 naming the key is at api.py:196-202 (HIGH); the contract docstring is api.py:24-40 and the judge-exemption sentences are api.py:41-43 (HIGH); `SentinelClient.check` is api.py:358-374 (the cited 358-375 includes a trailing blank; fine); `_authorize` runs api.py:551-586, so the cited 551-585 omits the last line (the `return _refuse(...)`) by one; the handler block cited as 887-910 begins inside the F1 comment block and ends at the `_count(app, "passthrough")` line, so it is approximate (LOW).
- 401 on either header missing, naming both; 403 body fields `decision, clause_id, reasons, agent_id, action`; ESCALATE adds `escalation: true`; `retry_after_seconds` only when the sentinel context supplies it; 503 for sentinel unreachable, timeout, non-200, non-JSON body, no verdict, or `FIELD_SENTINEL_URL` unset; default action `llm.messages` (`EGRESS_ACTION`); the passthrough exemption only for `SELF_AGENT_IDS` and identity is still checked first (api.py:_authorize, 887-910) (HIGH, read in the code).
- "The shipped compose overlay mounts that directory read-only (`field-manifests`)": integration/demo/docker-compose.gb10.yml lines 67, 178, 251, 261 (HIGH).

## Mutants (doc-claim mutations on the head; suite: tools/tests/test_deploy_docs.py, the only test that names INTEGRATION.md; baseline 5 failed, 30 passed, identical on base 5808a5cd, environment failures, not counted as kills)
| # | Mutant | Result | Killed |
|---|---|---|---|
| 1 | citation `mode.py:34-47` -> `34-99` | 5 failed, 30 passed | no |
| 2 | accepted spelling `logonly` -> `on` | same | no |
| 3 | `enforced` spelling dropped | same | no |
| 4 | 401 now "only the token header missing" | same | no |
| 5 | 403 now "BLOCK only" | same | no |
| 6 | `escalation: true` -> `false` | same | no |
| 7 | `retry_after_seconds` "always appears" | same | no |
| 8 | default action `llm.messages` -> `llm.chat` | same | no |
| 9 | judge exemption "for every" agent | same | no |
| 10 | citation `doa.py:40` -> `doa.py:400` | same | no |
| 11 | read-only volume name `field-manifests` -> `field-keys` | same | no |
Totals counted from the table: 11 mutants, 0 killed, 11 survived. Survivors run against the whole suite: no test other than test_deploy_docs.py names the file; I did not run the other suites. As the claims were verified by reading the code, survivors are expected for prose; I treat them as LOW, in line with the C-1187 ruling on checklist prose.

## Findings
- F-C577-1 LOW: no test pins the new enforce-mode paragraph or the mode spellings (mutants 2-9); a drift in the code would not turn anything red.
- F-C577-2 LOW: two citations are off by a line or approximate (`api.py:551-585` ends one line early; `887-910` starts mid-comment); the banner already tells readers to re-check.
- F-C577-3 LOW: objection 2, duplicated contract text.

## Verdict: PASS on 25ffdc11022c6b8ae655fef5d3b4548499aebe3a
Head frozen; LOWs go in a NEW PR. Merge clean against current main (base 5808a5cd is old). CI green and a GX10 light run "docs only" on the exact head rebased on current main. Not run by me: CI, GX10.
