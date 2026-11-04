# Review PR 612 @ e7249caf76d38893f62fb3eb443c9b9867e50f07 (rebuild of #465, runbook section 7 "what is on main") - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head e7249caf. Docs only (light GX10 run allowed, "light run, docs only"). UNVERIFIED (cloud, no GX10).

## Objections first
1. The paragraph's method ("checked against main 6385f877 by git log subjects, each item a merged PR number from those subjects") cannot be reproduced on this repository: origin/main holds 108 commits starting at 83ff023e (30 Oct) and NO subject names `#23`..`#50` (I grepped subject and body for each of the 13 numbers: zero hits). The PR numbers are therefore "not in source" for me; they rest on GitHub's PR list.
2. The text says "checked against main 6385f877"; main is 97dcfec1 now. The head contains main (ancestor check passes), 6385f877 is an ancestor of main, so the label is stale but not wrong for those items.
3. Rewriting a status paragraph invites false "merged" claims; every claim was therefore checked against the code, not the numbers.

## Facts (HIGH unless tagged)
- Head fetched via refs/pull/612/head = e7249caf, 1 commit, contains origin/main, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. Diff: `docs/runbooks/v1.2-deploy-rollback.md`, +19 -17, one paragraph; the only non-ASCII character added is `§` (checked).
- Each "Merged" item checked in the code on main:
| Item | Evidence on 97dcfec1 | Result |
|---|---|---|
| `tools/phase_g_check.py` (#28) | file exists | present |
| `--operator-id` on renew_token, provision_ssl_agents, estate_probe (#36, C-2) | grep counts 4, 4, 3 | present |
| service CLIs with `--operator-id` (#36) | 3 service `cli.py` files | present (the text says "the service CLIs"; I counted 3) |
| DOA job grantors (#36, C-13) | `grantor` in delegation-authority cli.py and api.py | present |
| compose flag plumbing (#26) | `FIELD_OPERATOR` appears 23 times in `integration/demo/docker-compose.yml` | present |
| key-file read C-1 (#32) | `ENV_OPERATOR_KEY_FILE`, `MAX_KEY_FILE_BYTES` in operator_auth.py | present |
| ledger `operator.refused` C-16 (#32) | referenced in sealed-ledger api.py:284 | present |
| GB10 TLS listener phase 1 (#30, section 8) | TLS lines in the runbook, caddy test file passes | present |
| console refuses an operator key outside a secure context C-20 (#50) | console.html:758, ops-console README row, harness test | present |
| Fly per-process identities C-5 (#44) | `FIELD_OPERATOR` in `integration/fly/entrypoint.sh` | present (one file; not read in depth) |
| guards (#23), B-6 directory mounts (#29), Stage 0 callers (#33, #42), guards slice (#41), follow-ups (#46) | `test_operator_mounts_b6.py` and `test_phase_g_check.py` pass; the rest only by the doc tests | not individually traced |
- "I do not know whether C-20 tools half is on main": I can answer for renew_token. `tools/renew_token.py` still refuses cleartext only for a non-loopback, NON-PRIVATE base (line ~124 docstring; ~1581-1584: "use https:// or a loopback/private address"), so the private-address exemption is still there with a key present: NOT narrowed in that tool (HIGH). Other tools not checked. The paragraph's "I do not know" is correct and conservative.
- Tests that read this runbook: `test_runbook_pins_c465.py`, `test_deploy_docs.py`, `test_phase_g_check.py`, `test_operator_mounts_b6.py` = 168 passed on the head (with `packages/field-agent/src` on the path; without it `test_deploy_docs.py::test_the_gb10_override_runs_the_x3_canary_agent_scoped...` fails on `ModuleNotFoundError: field_agent`, on main as well as on the head: an environment baseline, not a regression, not counted as a pass). No test pins the paragraph's PR numbers.

## Findings
- F-R612-1 MEDIUM-LOW: PR numbers #23-#50 are unverifiable from this repository (see objection 1). Condition below.
- F-R612-2 LOW: label "main 6385f877" is stale (main is 97dcfec1).
- F-R612-3 LOW: the paragraph correctly says some `Status: pending` lines below it are not re-read; I did not read them.

## Mutants
Not applicable (prose, no code). No test would catch a wrong PR number.

## Conditions
1. The coordinator confirms the thirteen PR numbers against GitHub's merged-PR list (I have no source for them here).
2. Docs-only: a light GX10 run is allowed; CI full set must be green.
