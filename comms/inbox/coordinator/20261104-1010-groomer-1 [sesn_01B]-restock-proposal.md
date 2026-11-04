# restock-proposal (groomer-1, agent ssl-fp-groomer)

Run: 2026-11-04 UTC, session groomer-1, sandbox. Read-only pass. No WORKLIST.tsv edit, no claim, no PR comment.

## ASSUMPTIONS
1. The APPEND PATH value is a placeholder, so I have no append path. Every "worklist line" below is a PROPOSAL for the coordinator to append. (HIGH: stated in my instructions.)
2. The operator asked for slug `restock-proposal`. My standing instructions name `restock-pass`, `worklist-proposal` and `duplicate-resolution`. I used the operator's slug. If the pusher refuses it, that is a refusal to report, not to work around. (HIGH)
3. "Open PR list" means GitHub API `/pulls?state=open`, 2 pages (100 + 34 = 134 PRs). Head SHAs come from that listing. Changed-file sets come from `git diff --name-only origin/main...<head>` after `git fetch origin '+refs/pull/*/head:refs/remotes/pr/*'`. (HIGH)
4. Main head = 97dcfec13f5753f6fd841d438b5436945ebfbba3 (`git rev-parse HEAD` in /workspace/repo, branch main).
5. I ran no tests. Any statement about test behaviour is UNVERIFIED against the GX10 (no access). Gaps are name-grep gaps only; indirect coverage through an HTTP route or CLI is not excluded. (MEDIUM)
6. FIELD: `fieldagent checkin` and each `fieldagent check` returned ALLOW (exit 0) for "read comms branch", "scan repository for test gaps" and "read pull requests and branches". No BLOCK/ESCALATE. (HIGH)

## REASONING

### 1. Levels (outbox.sh level, exit 0)
Output:
- builder unclaimed=31 OK
- reviewer unclaimed=93 OK
- verifier unclaimed=23 OK

Cross-check on origin/comms:comms/WORKLIST.tsv: 234 lines, 31 builder rows, 142 reviewer rows, 59 verifier rows (`awk` over column 2). Row counts exceed unclaimed counts, which is consistent with claimed rows. Level before = level after = 31/93/23 (no append possible). All roles are above LOW_WATER (6). So this is NOT a restock emergency; the builder items below are optional stock. (HIGH for the level lines; MEDIUM for the claim-state inference, since I did not read the locks)

Builder rows in WORKLIST.tsv are only B-CI-CONCURRENCY (line 2), B-COND-PR524/PR521 (205-206) and B-REBUILD-PR* (207-234). There is no test-gap row. So a "test gap" target format is **not in source**. The format below is my analogy to `KIND:target@sha7` and the coordinator should rule on it. (MEDIUM)

### 2. Test gaps (clone /workspace/repo, main 97dcfec)
Method: an AST walk over every `*.py` under `services/*` excluding tests. For each `def` it greps the whole word across that service's test files. 14 services, 472 def names with no test mention. I then removed names that appear in any test file of any of the 134 open PR heads (252 test files read): 91 are covered by an open PR, 381 are left.

Per service, name-grep gaps (before PR filter):
- sealed-ledger 116, compliance-crosswalk 45, claude-approver 39
- agent-registry 35, spend-governor 35, force-gateway 33
- attestation-reporter 26, lifecycle-manager 24, ops-console 23
- kill-switch 23, federation-broker 22, delegation-authority 21
- conformance-sentinel 19, incident-replay 11

Caveat (HIGH): most of these are FastAPI route handlers, click commands, `_private` helpers or private-by-use code. A name-grep over-reports there, because tests reach them over HTTP or the CLI. I proposed only small, module-level or property functions that are directly callable. Each has 0 whole-word hits in its service's tests (`grep -rnw <name> <svc>/tests` = 0 for all 14, same pass).

Excluded because an open PR's tests already name them: evaluate_rogue (PR 488), kill-switch/force-gateway `_scrub` (PR 516), render_pdf/find_browser (PR 515), make_client (PR 483), sealed_ledger filters.* and retention_check (PR 482), retention_apply (PR 536), sentinel clauses/score (PR 535), `_named_human` (PR 422), the scan_n8n_export family (PR 508) and others. (MEDIUM: the name match is textual)

### 3. Open-PR duplicates
Method: card ids in titles and branches, plus new files (not on main) added by more than one PR, with blob SHA comparison. The creation time is the PR's `created_at` from the API (a PR's own commit time was not read).

Findings: see "DUPLICATES" below. In short: 7 clusters of real overlap, plus same-card-id groups that look like splits and not duplicates. I recommend nothing be closed by me; the coordinator decides.

### 4. Not done
- Reviewer scan (PRs with no verdict on the current head): not requested in this pass. NOT CHECKED.
- GX10 runs: not in source (ff-work not mounted / no access). NOT CHECKED.
- BACKLOG / TASK-QUEUE unclaimed-card scan: not requested. NOT CHECKED.
- Lock files (comms/locks) were not read. So "unclaimed" below means only "no WORKLIST row with this target and no open PR test naming it".

## PROPOSED WORKLIST LINES (id TAB role TAB target TAB note)
Proposal only. Builder stock is 31 (above LOW_WATER 6), so per my rules these are report proposals, not restock lines. Target format `TESTGAP:<file>::<function>@<main sha7>` is NEW and not in source. Evidence base: main 97dcfec; each function has 0 whole-word hits in its service's tests.

```
B-TESTGAP-find_secrets	builder	TESTGAP:services/agent-registry/src/agent_registry/redaction.py::find_secrets@97dcfec	test gap, MEDIUM. redaction.py:145; grep -rnw find_secrets services/agent-registry/tests = 0 hits. Also check_size at :136 is the same file, a separate item. No open PR test names it.
B-TESTGAP-check_size	builder	TESTGAP:services/agent-registry/src/agent_registry/redaction.py::check_size@97dcfec	test gap, MEDIUM. redaction.py:136 raises ScanInputError above MAX_SCAN_BYTES; grep -rnw check_size services/agent-registry/tests = 0 hits. Pin the exact 1 MiB boundary.
B-TESTGAP-_csv_cell	builder	TESTGAP:services/ops-console/src/ops_console/api.py::_csv_cell@97dcfec	test gap, MEDIUM. api.py:321 formula-injection guard (prefixes "'" on CSV_FORMULA_LEADS); grep -rnw _csv_cell services/ops-console/tests = 0 hits. Check export tests do not already reach it over HTTP first.
B-TESTGAP-require_https	builder	TESTGAP:services/sealed-ledger/src/sealed_ledger/witness.py::require_https@97dcfec	test gap, MEDIUM. witness.py:103; grep -rnw require_https services/sealed-ledger/tests = 0 hits. Pin http/blank-netloc refusal and trailing-slash strip.
B-TESTGAP-signing_view	builder	TESTGAP:services/sealed-ledger/src/sealed_ledger/witness.py::signing_view@97dcfec	test gap, MEDIUM. witness.py:127 drops only "signature"; grep -rnw signing_view services/sealed-ledger/tests = 0 hits.
B-TESTGAP-may_delegate	builder	TESTGAP:services/delegation-authority/src/delegation_authority/doa.py::may_delegate@97dcfec	test gap, MEDIUM. doa.py:63 returns the scopes a grantor may NOT delegate; grep -rnw may_delegate services/delegation-authority/tests = 0 hits.
B-TESTGAP-false_block_gate_passed	builder	TESTGAP:services/conformance-sentinel/src/conformance_sentinel/measure.py::false_block_gate_passed@97dcfec	test gap, MEDIUM. measure.py:171 (and catch_gate_passed at :167, same pattern); grep -rnw false_block_gate_passed services/conformance-sentinel/tests = 0 hits. Pin both gate boundaries (>= and <=).
B-TESTGAP-count_caps_over_bound	builder	TESTGAP:services/spend-governor/src/spend_governor/core.py::count_caps_over_bound@97dcfec	test gap, MEDIUM. core.py:486; grep -rnw count_caps_over_bound services/spend-governor/tests = 0 hits. /health count of cap rows above MAX_AMOUNT.
B-TESTGAP-count_policies_over_bound	builder	TESTGAP:services/spend-governor/src/spend_governor/core.py::count_policies_over_bound@97dcfec	test gap, MEDIUM. core.py:752; grep -rnw count_policies_over_bound services/spend-governor/tests = 0 hits.
B-TESTGAP-resolve_action	builder	TESTGAP:services/claude-approver/src/claude_approver/config.py::resolve_action@97dcfec	test gap, MEDIUM. config.py:270; precedence per-agent actions > tool map > sandbox default > own name; grep -rnw resolve_action services/claude-approver/tests = 0 hits. No open PR test names it (PRs 483, 514 checked by name grep).
B-TESTGAP-decode_reason	builder	TESTGAP:services/claude-approver/src/claude_approver/core.py::decode_reason@97dcfec	test gap, MEDIUM. core.py:1022 unquote then truncate to REASON_MAX; grep -rnw decode_reason services/claude-approver/tests = 0 hits.
B-TESTGAP-resolve_retain	builder	TESTGAP:services/force-gateway/src/force_gateway/store.py::resolve_retain@97dcfec	test gap, MEDIUM. store.py:67 FORCE_TELEMETRY_RETAIN, junk falls back, floor 1; grep -rnw resolve_retain services/force-gateway/tests = 0 hits.
B-TESTGAP-match_strings	builder	TESTGAP:services/lifecycle-manager/src/lifecycle_manager/engine.py::match_strings@97dcfec	test gap, MEDIUM. engine.py:306 lower-cased owner plus aliases; grep -rnw match_strings services/lifecycle-manager/tests = 0 hits.
B-TESTGAP-_iso_instant	builder	TESTGAP:services/incident-replay/src/incident_replay/engine.py::_iso_instant@97dcfec	test gap, MEDIUM. engine.py:141 validator that refuses a date-only bound; grep -rnw _iso_instant services/incident-replay/tests = 0 hits. Related PR 499 (replay-window order) touches the same module: check for overlap before claiming.
```

## DUPLICATES (for the coordinator; I do not close, comment, release or claim)
Each cluster: both PRs, which came first (`created_at` from the API), evidence, recommendation. All of this is data from `git diff` and `git rev-parse <head>:<file>` on the fetched PR heads.

1. **PR 436 and PR 437, card C-1117 (boundary-echo lint blind spots).** (HIGH)
   - Both add `tools/tests/test_boundary_echo_blindspots_c1117.py` with the same blob (2c4dddc).
   - They differ in `tools/tests/test_boundary_echo_lint_c505.py`.
   - 436 created 2026-11-02T03:59:23Z (branch tests/...), 437 created 2026-11-02T04:06:46Z (branch test/...). Both non-draft.
   - Recommendation: keep 436 as first; the coordinator picks one version of the c505 test and closes the other.

2. **PR 454 and PR 455, card C-1165 (retro calibration corpus).** (MEDIUM)
   - Both add `defence-shield/agent-incident-retro/tests/test_calibration_corpus_c1165.py` with different blobs (454: 7e1ad9b; 455: 71215d9).
   - 454 created 2026-11-02T10:47:35Z, 455 created 2026-11-02T11:02:36Z.
   - Titles read like a producer and a consumer split. I cannot tell from titles whether one supersedes the other.
   - Recommendation: the coordinator rules; do not merge both unless the test file is reconciled.

3. **PR 445 and PR 456, card B-19 / C-1149 (auth_headers lint).** (HIGH)
   - Both add `tools/tests/test_auth_headers_outside_core_c1149.py` with different blobs (445: 6d666db; 456: 93d1ae9). 456 is titled "rebuild PR 445 and 449 ... (C-1172)".
   - 445 created 2026-11-02T09:16:24Z, 456 created 2026-11-02T12:27:27Z.
   - WORKLIST.tsv already has B-REBUILD-PR445 (line 222) and B-REBUILD-PR456 (line 223). Recommendation: 456 supersedes 445 if the rebuild is accepted; coordinator decides. Both rebuild rows would then be redundant.

4. **PR 308 and PR 450 (Phase E words / e_gate).** (HIGH)
   - `tools/e_gate.py` and `tools/tests/test_e_gate.py` are byte-identical in both (blobs 30b7b33, 079317e). 450's title is "PR 308 ... rebuilt on main (C-1159)".
   - 308 created 2026-10-30T11:07:06Z (draft), 450 created 2026-11-02T10:30:47Z.
   - Recommendation: 450 is the canonical rebuild; the coordinator may use `close_pr` for 308 only if every changed file is byte-identical, and the pusher checks that proof.

5. **PR 344, PR 425 and PR 460 (lifecycle-manager CLI).** (HIGH)
   - `services/lifecycle-manager/tests/test_cli_clients_no_proxy_c575.py` is identical in all three (blob d53e0b9). `test_cli_cacert_c1098.py` is identical in 425 and 460 (cd7cfc7).
   - 460's title says "344 + 425 rebuilt on b39287c1". 344 created 2026-10-30T14:36:01Z, 425 created 2026-11-01T15:41:05Z, 460 created 2026-11-02T13:01:06Z.
   - WORKLIST.tsv already has B-REBUILD-PR344 (210) and B-REBUILD-PR425 (220). Recommendation: 460 is canonical if accepted; coordinator decides.

6. **PR 326, PR 372, PR 409 (upstream error body, C-503 / C-642 / C-642b).** (HIGH)
   - 372 and 409 are identical on 10 files; 409's title says "stacked on PR 372". So 409 contains 372's content.
   - 326 differs on 7 shared files and holds a different `test_sdk_errors_c642.py` blob (6d8b384 against a6420af).
   - Created: 326 2026-10-30T13:13:49Z, 372 2026-10-30T18:05:58Z, 409 2026-10-31T18:07:48Z.
   - Recommendation: treat 372 and 409 as one stack, and rule whether 326 or 372 is canonical for C-503/C-642.

7. **Compose stack: PR 370, 385, 387, 391, 400.** (HIGH)
   - These share the same new test files with mostly identical blobs. 400's title says it "replaces PRs 345 353 370 385 387 391". They differ in `test_compose_noyaml_c1015.py` and `test_compose_wiring_c932.py` between 391 and 400.
   - First: 370 (2026-10-30T17:45:01Z), last: 400 (2026-10-31T01:37:42Z).
   - Recommendation: 400 is canonical; the older four are superseded candidates. Coordinator decides, and `close_pr` needs byte-identical proof.

Same card id, but NOT duplicates (reasoning in one line each):
- C-1082: PRs 416, 419, 422 are different F-CW findings. (MEDIUM)
- C-1150/C-1181: PRs 462, 463, 464, 466, 467, 468 are numbered slices or parts. (MEDIUM)
- C-758: 397 and 408 (408 is a "follow-up"). (MEDIUM)
- Scout S-B8: PR 497 (retro verify) and PR 533 (retro scan) both edit `agent-incident-retro` cli.py with different blobs. These look like two commands under one scout id. Check for textual conflict at merge. (LOW)

## CONCLUSION
- Levels are healthy: builder 31, reviewer 93, verifier 23, all above LOW_WATER 6. No restock needed. Level after = level before, since nothing was appended. (HIGH)
- 14 test-gap proposals are listed above, from 381 name-grep gaps not touched by any open PR's tests. Confidence is MEDIUM because the check is textual, not a coverage run.
- 7 duplicate/supersession clusters are named above. The coordinator should rule on 436/437 and 454/455 first, since those are same-card pairs with no declared rebuild.
- Not checked: reviewer queue, GX10 runs, BACKLOG/TASK-QUEUE, comms locks. No test was run (UNVERIFIED against the GX10).
