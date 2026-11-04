# Reviewer report: PR 380 @24d5482b (field-mcp PR 2: Tier 2 write tools, seven, in a separate write process)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13. 37 commits, 36 files, +5178 (of which snapshot.json 1722 and field-mcp-hashes.txt 340 are generated). This is the biggest review of my session; I reviewed the Tier 2 write path (tools.py, audit.py, config.py, client.py write branches, catalog.py Tier 2 entries) with mutants. I did NOT review: the Tier 1 read tools beyond the tests that ran, snapshot.json content, integration/field-mcp-hashes.txt and the constraints changes (supply-chain pins), the CI workflow edit, or the unrelated `integration/demo/fixtures/kr-edge/check_edge_block.py` diff (-79 lines) in the PR range.

## Verdict: PASS WITH CONDITIONS (head 24d5482b1425a70854e02c5ceabe958df9b73704)
Conditions: C1 pin the intent-to-outcome linkage (F1, mutant W16): a write whose outcome row carries a different call id than its intent row passes every test, so an auditor could not join the two rows. C2 pin that `rename_agent` refuses any body property other than `name` at the SCHEMA layer (F2, mutant S6): dropping `additionalProperties: false` from the narrowed body lets `status`, `owner` and the rest through the tool schema, and nothing in the 424-test suite notices; the README's "cannot send status, owner, domain or manifest_ref" is then held only by the catalog line and the upstream. Both are one-test fixes. C3 rebase and re-run: main is 97dcfec1 (this head merges cleanly by `git merge-tree`, but 8 merges moved); GX10 16/16 on the exact rebased head, CI green. C4 a separate reviewer or Don reads the generated supply-chain pins (hashes, constraints) and the CI change: I did not. No blocking code defect in the write path.

## Objections first
1. No human confirmation exists and the README says so ("Not a confirmation mechanism ... not a security boundary"): the model can call any Tier 2 tool whenever `ffmcp-write` runs. The controls are audit-first, a reason, a rate limit and a narrow tool list. The shared platform secret authorises the same writes directly (README, read). Accepted by the design, stated; not mine to waive (HIGH).
2. Write tools exist for `registry create_agent`, `ledger export`, and `sentinel check` (spends the agent's spend windows). `sentinel check` and `crossing` record a verdict row; a flood within the rate limit (default 10 per minute, Don's ruling) fills the append-only ledger at 10 rows per minute per process; the per-process limit means N processes multiply it (MEDIUM, reasoned; I did not run two processes).
3. The intent row is appended before the call, the outcome row best effort. A crash between the two leaves an intent with no outcome; the result reports `not_recorded` when the outcome append fails, and W14 (always "recorded") is killed (HIGH, run).
4. The reason string is model-chosen text that lands on a sealed ledger forever; clean_reason strips format characters and fillers and caps at 300 (S2 killed) (HIGH, run). Prompt-injected reasons are data, bounded.
5. A 5xx or oversize or transport error on a write returns "unknown outcome", never a plain failure, so a retry is a human decision (K1, K3, K4, K5 killed) (HIGH, run).
6. The first mutant pass missed test_merge_368_380.py (my list omitted it); W3, W4, W5 survived there and were killed once that file ran, as the commit message says (HIGH, run, corrected below).

## Scope and identity
37 commits; author AND committer on every one = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py` is absent at this head's base, so not run. No credential, address or flag value seen in the source I read; all test keys are made up.

## Runs
Baseline (unmutated head): whole field-mcp suite `tests` 424 passed in 142 s (with `mcp` and `jsonschema` installed into my own interpreter; no repo file changed). Mutants edit src/field_mcp one at a time in three scratch copies. Pass 1 used the ten Tier 2 test files (kill = any failure, with -x); survivors, plus two rows that had not applied or crashed, were re-run against the whole suite. Files restored (git status clean in every copy).

## Mutants (59)
Behaviour groups: audit-first write path W (16), audit record A (9), rate limit R (4), config C (11), schema and catalog S (11), client write branches K (5), dispatch D (3).

| Id | Mutation | Result |
|---|---|---|
| W1 | no audit object tolerated | KILLED |
| W2 | unencodable args accepted | KILLED |
| W3 | agent id check removed | KILLED (test_merge_368_380.py; survived pass 1 without it) |
| W4 | agent id `match`, not `fullmatch` | KILLED (same) |
| W5 | agent id length not bounded in code | KILLED (same) |
| W6 | blank reason accepted | KILLED |
| W7 | rate limit not applied | KILLED |
| W8 | reason stored uncleaned | KILLED |
| W9 | failure outcome not recorded | KILLED |
| W10 | bug between intent and reply no longer unknown_outcome | KILLED |
| W11 | operator pair sent on every write route | KILLED |
| W12 | operator pair never sent | KILLED |
| W13 | write flag not passed upstream | KILLED |
| W14 | missing outcome reported as recorded | KILLED |
| W15 | tier 2 treated as a read (no audit) | KILLED |
| W16 | outcome uses another call id than the intent | SURVIVED (full suite 424 passed) |
| A1 | raw body in the intent row | KILLED |
| A2 | reason missing from the intent row | KILLED |
| A3 | operator missing from the intent row | KILLED |
| A4 | client name unbounded | KILLED |
| A5 | outcome status missing | KILLED |
| A6 | outcome failure reported as recorded | KILLED |
| A7 | ledger error text passed through | KILLED |
| A8 | ledger row has no agent id | KILLED |
| A9 | reason also copied into `targets` | SURVIVED (harmless duplicate, bounded 300; LOW) |
| R1 | window edge `>` not `>=` | KILLED |
| R2 | one extra call allowed | KILLED |
| R3 | refused attempts also recorded | KILLED |
| R4 | window ten minutes | KILLED |
| C1 | write flag not required | KILLED |
| C2 | one blank half of the operator pair tolerated | KILLED |
| C3 | ledger not required | KILLED |
| C4 | rate upper bound 6000 | KILLED |
| C5 | rate zero allowed | KILLED |
| C6 | default rate 100 | KILLED |
| C7 | operator key not in the redaction set | KILLED |
| C8 | external cleartext allowed with the flag | KILLED |
| C9 | operator key not header-checked | KILLED |
| C10 | service keys not header-checked | KILLED (first form of the mutant was a syntax error and was redone with `pass`) |
| C11 | half a caller identity tolerated | KILLED |
| S1 | reason not required in the schema | KILLED |
| S2 | reason max 3000 | KILLED |
| S3 | id bound 2000 | KILLED |
| S4 | agent id pattern open | KILLED |
| S5 | narrowed body properties not required | KILLED |
| S6 | narrowed body allows extra properties | SURVIVED (full suite; F2) |
| S7 | tier filter widened (control; tier 3 absent from the catalog) | SURVIVED, EQUIVALENT |
| S8 | rename_agent can send status | KILLED |
| S9 | regwatch_check sends the operator pair | KILLED |
| S10 | export offers out_dir | KILLED |
| S11 | form id has no segment pattern | KILLED |
| K1 | 500 not unknown_outcome | KILLED |
| K2 | a read 5xx also unknown_outcome | KILLED |
| K3 | oversize write reply as plain error | KILLED |
| K4 | not-sent errors read as unknown outcome | KILLED |
| K5 | write transport errors never unknown outcome | KILLED |
| D1 | tier 2 body-id wording | KILLED |
| D2 | schema validation removed | KILLED |
| D3 | unexpected exception escapes `call()` (only RuntimeError caught) | SURVIVED (LOW: no test raises another exception type from inside a tool call) |

Counted from the table: 59 rows (W 16, A 9, R 4, C 11, S 11, K 5, D 3). KILLED 54, SURVIVED 5: W16, A9, S6, D3 real, S7 equivalent. Kill rate on non-equivalent rows 54 of 58 = 93%. Per group: W 15/16, A 8/9, R 4/4, C 11/11, S 10/10 non-equivalent... precisely S 9 of 10 non-equivalent (S6 survives; S7 equivalent), K 5/5, D 2/3.

## Findings
- F1 MEDIUM (HIGH confidence, run): W16, condition C1. Add an assertion that the outcome row's `call_id` equals the intent row's and that two calls get different ids.
- F2 MEDIUM (HIGH, run): S6, condition C2. Add `{"name": "x", "status": "decommissioned"}` to the refused set for `agent_registry_rename_agent` and assert nothing is sent.
- F3 LOW: A9, D3.
- F4 LOW: objection 2, a per-process rate limit.
- F5 INFO: the PR's own `scripts/mutants.py` (196 lines) exists; I did not run it, I wrote an independent set.

## Not verified
Tier 1 read tools; snapshot.json; field-mcp-hashes.txt and constraints pins; the CI workflow and kr-edge fixture changes; rebase on 97dcfec1; CI; GX10; any real service or MCP client (README: "Not verified against any real service, estate or MCP client").
