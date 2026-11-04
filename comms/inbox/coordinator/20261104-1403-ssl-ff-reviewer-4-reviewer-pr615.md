# Reviewer report: PR 615 @ 5cb43728f438c6eef27fbc4e3a0b8bb1d111c98a (rebuild of #471: the field-mcp service, Tier 1 reads and Tier 2 audited writes)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). One commit batch on origin/main 97dcfec1 (the current tip): 38 commits, 37 files (+5179/-2): a new service services/field-mcp (src: tools.py, audit.py, client.py, config.py, catalog.py, hosts.py, server.py, snapshot.json 1722 lines; 19 test files; README; scripts) and one allowlist line in tools/tests/boundary_echo_allowlist.txt. `git merge-tree --write-tree origin/main pr615` clean (HIGH). Author and committer of all 38 = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). Trailers: 31 Sonnet 5.5, 7 Fable 5.1 (see objection 1). The CI install lines for field-mcp (hash-checked closure) are already in the base's ci.yml.

## Objections first
1. PROCESS: 7 of the 38 commits carry `Co-Authored-By: Claude Fable 5.1` (044743f7 b449e953 ec083d8c 06cca07c 79ecd04b 2da0c143 9d3ed019 ); the standing rule for every lane is Opus/Sonnet/Haiku, never Fable (HIGH that the trailers are present; MEDIUM that a Fable session wrote them). Coordinator ruling needed; I did not and cannot rewrite history.
2. This is an MCP server that lets a language model make audited WRITES to the platform (kill, revoke, caps, ...) with the operator identity: the worst failures are a write without its intent record, a write that a model can redirect to another path, an operator key in a result, and a retry after an unknown outcome. The mutants below attack exactly those.
3. Size: 5179 lines; I mutated and read the write path (tools.py `_write`, `_call`, schema building), the audit module, the HTTP client and the config loader; I did NOT line-review catalog.py (the tool table), server.py (the stdio wiring), scripts/ or the 1722-line generated snapshot.json beyond what the route-coverage and snapshot tests assert. Coverage statement, not a claim about those files.
4. Python 3.11+ and mcp==2.3.0 / mcp-types==2.3.0 are pinned; I installed them from the package index into a scratch venv to run the tests (they resolved), but I did not verify the hashes in integration/field-mcp-hashes.txt.

## Verified (run by me)
- Baseline on the exact head (relative PYTHONPATH with every service's src; pytest-xdist -n 4 for speed): services/field-mcp/tests 424 passed (145 s serial, 26-40 s parallel).
- `tests/test_route_coverage.py` (14 tests) passes when all service sources are on the path: every live route of the services is a tool or explicitly excluded.

## Mutants (mutations of the field-mcp sources; scratch worktree on the head; baseline 424 passed; kill = at least one failure; `-x -n 4`)
Write path (tools.py): T1 audit missing no longer stops a write; T2 unencodable args not refused; T3 agent-id pattern accepts a trailing newline (match for fullmatch); T4 agent-id cap 200 -> 2000; T5 agent-id check removed; T6 blank reason accepted; T7 rate limit not applied; T9 operator headers sent on every route; T10 operator headers never sent; T12 outcome not recorded on a ToolError; T13 not recorded on an unexpected error; T14 unexpected error reports a plain failure instead of "outcome unknown"; T15 result says outcome recorded when it was not; T16 Tier 1 id message changed; T17 body-id check skipped; T18 `ID_FIELD` matches any name ending in "id"; T20 reason not required; T21 reason cap 300 -> 3000; T22 Tier 2 string arguments not length capped; T23 unknown tool no longer refused.
Audit (audit.py): A1 format characters kept; A2 blank fillers kept; A3 control characters kept; A4 reason not trimmed; A5 rate window 60 s -> 6 s; A6 rate limit `>=` -> `>`; A7 a refused attempt still uses a slot; A8 body hash omitted; A9 body stored in the record; A10 client name not truncated; A11 operator missing from the record; A12 append failure leaks its cause; A13 outcome failure raises; A14 intent agent id taken from the body first.
Client (client.py): C1 5xx on a write reported as a plain status; C2 transport error after the send reported as "unreachable"; C3 redirects followed; C4 proxy environment read; C5 size cap removed; C6 secrets not redacted in results; C7 single-string cap removed; C8 path segment allows a slash; C9 dot segments allowed; C10 build_path uses match; C11 untrusted-data flag dropped.
Config (config.py): G1 write process starts without the write flag; G2 without an operator; G3 without a ledger; G4 rate bound 600 -> 6000; G5 operator key not in secrets(); G6 header-unsafe operator accepted.
Totals counted from the 51 result lines: 51 valid mutants, 48 killed, 3 survived (T16, T18, A14). Not built or not applied, so excluded: T8, T11, T19 (my script did not build them), C12 (pattern did not apply). The 3 survivors were run against the whole services/field-mcp suite (that is the 424 tests above); nothing outside it imports the service.

## Reading of the survivors
- T16: the Tier 1 body-id refusal wording ("argument refused" vs "arguments refused"): the schema pattern refuses the same inputs first, so the code check is a second layer whose wording is not observable on the tested inputs; LOW, probably equivalent.
- T18: `ID_FIELD` over-matches names that merely end in "id" (for example "valid"); the over-match would only refuse more, never less, so it is a pin gap, not an exposure; LOW.
- A14: the order in which the intent row takes its agent id (top-level argument or body) is not pinned; LOW (in practice both are equal or only one is present).

## Findings
- F-MCP-1 PROCESS: Fable trailers on 7 commits (objection 1).
- F-MCP-2 LOW: T16, T18, A14 unpinned (above).
- F-MCP-3 note: objection 3 and 4, coverage and hash verification not done by me.

## Verdict: PASS WITH CONDITIONS on 5cb43728f438c6eef27fbc4e3a0b8bb1d111c98a
The behaviours that matter for a model-driven write path hold under mutation (48 of 51, the 3 survivors LOW). Conditions: (1) coordinator ruling on the Fable trailers; (2) CI green and the full GX10 run on this exact head (a new service: not a light run) rebased on current main; (3) hash check of integration/field-mcp-hashes.txt by whoever installs it (I did not); head frozen after this PASS, LOWs go in a NEW PR. Not run by me: CI, GX10, the real MCP clients.
