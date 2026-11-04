# Reviewer report: PR 624 @3514b5f4 (kill-switch CLI: an unreachable service is one line, ids are quoted path segments, S3-4)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator). Head 3514b5f4 is a merge of main (b963407a, also the PR base) onto the fix commit 3d97cbe4; the code content is the fix commit's. A second worklist line, if one exists for 3d97cbe4, is covered by this report (same code and tests).

## Verdict: BLOCK (head 3514b5f4e20666a1a838ddb40a50ee85107361d3)
Two defects in the operator kill CLI, both reproduced by running the head (not by reading only). Both fixes are small; after them this head would be PASS WITH CONDITIONS on the usual rebase, GX10 and CI conditions.

- B1 HIGH (run): a write whose reply is lost after the request was sent prints "nothing was changed". `_request` (services/kill-switch/src/kill_switch/cli.py, the `except httpx.HTTPError` branch) adds "; nothing was changed" for EVERY `httpx.HTTPError` on a write. I ran the head over `httpx.MockTransport` with the handler raising `ReadTimeout` on `agent a1` (a kill) and `RemoteProtocolError` on `revive a1`: both exit 1 with "error: kill-switch unreachable (ReadTimeout); nothing was changed" and "... (RemoteProtocolError); nothing was changed". After a read timeout or a dropped connection the kill or revive may have been APPLIED by the service; the operator is told it was not. The test only drives `ConnectError` (a not-sent failure). The sibling code in field-mcp (client.py) already separates not-sent errors from the rest for exactly this reason. Fix: say "nothing was changed" only for errors where nothing was sent (connect errors, connect timeouts, unsupported protocol); otherwise say the outcome is unknown and name the status read to check.
- B2 MEDIUM (run): "ids are one encoded path segment" is false for dot segments. `_q` is `urllib.parse.quote(segment, safe="")`, which leaves `.` and `..` unchanged, and httpx normalises them: `heartbeat ..` sent `GET /`, `heartbeat .` sent `GET /heartbeat`; `%2e%2e` was double-encoded and stayed a segment (`/heartbeat/%252e%252e`). So an id of `..` retargets a read or a write to another route (`domain ..` would POST to `/kill`, `agent ..` to `/`). Impact is bounded (an operator types the id; the service answers 404/405 on those paths in my reading, not run), but the PR states the opposite invariant. Fix: refuse `.` and `..` ids before any request, or encode them (`%2E%2E`).

## Objections first (besides B1 and B2)
1. Only three of the seven id sites are pinned: drill, revive and checkin ids can be left unencoded and every test passes (Q5, Q6, Q8 below) (HIGH, run).
2. A mutant that handles only `ConnectError` (U5) passes all 288 kill-switch tests: a read timeout would then escape as a traceback, which is the failure the PR says it removes; no test uses a timeout (HIGH, run).
3. Timeouts of 30 s for domain and drill are unpinned (T1, T2 pass at 1 s). A kill of a whole domain that outlives its timeout is the B1 situation again (MEDIUM, run).
4. The unreachable message prints the exception CLASS only, never the URL or text: pinned (U1 killed) (HIGH, run). Good.
5. Reads (`heartbeat`, `liveness`) do not carry the note; W2 and U4 (a read marked write) survive, so a false "nothing was changed" on a read is unpinned (LOW).

## Scope and identity
2 files: services/kill-switch/src/kill_switch/cli.py (+44/-18), tests/test_cli_verbs.py (new, 106). 2 commits; author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py` was not run on this head (clean-merge check only).

## Runs
Baseline (unmutated head): test_cli_verbs.py 18 passed; full kill-switch suite 288 passed. B1 and B2: an inline script with `httpx.MockTransport` and the typer CliRunner, run on the head. Mutants edit cli.py one at a time; kill = test_cli_verbs.py fails; for survivors I ran the full suite; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| Q1 | path segment | slash left unencoded | KILLED |
| Q2 | path segment | no encoding | KILLED |
| Q3 | path segment | question mark left unencoded | KILLED |
| Q4 | path segment | hash left unencoded | KILLED |
| Q5 | path segment | drill id not encoded | SURVIVED (full suite too) |
| Q6 | path segment | revive id not encoded | SURVIVED (full suite too) |
| Q7 | path segment | kill id not encoded | KILLED |
| Q8 | path segment | checkin id not encoded | SURVIVED (full suite too) |
| Q9 | path segment | domain not encoded | KILLED |
| U1 | unreachable line | exception text echoed | KILLED |
| U2 | unreachable line | exit 0 on unreachable | KILLED |
| U3 | unreachable line | note never printed | KILLED |
| U4 | unreachable line | note printed on reads too | SURVIVED |
| U5 | unreachable line | only ConnectError handled | SURVIVED (full suite too) |
| N1 | killed body | non-object body accepted | KILLED |
| N2 | killed body | killed always False | KILLED |
| N3 | killed body | killed always True | KILLED |
| N4 | killed body | invalid JSON escapes | KILLED |
| W1 | write flag | kill not marked write | KILLED |
| W2 | write flag | heartbeat read marked write | SURVIVED |
| T1 | timeouts | domain timeout 1 s | SURVIVED |
| T2 | timeouts | drill timeout 1 s | SURVIVED |
| L1 | liveness | stale_after dropped | KILLED |

Counted from the table: 23 rows (path segment 9, unreachable line 5, killed body 4, write flag 2, timeouts 2, liveness 1). KILLED 15, SURVIVED 8, none equivalent. Kill rate 15 of 23 = 65%. Per behaviour: path segment 6/9, unreachable line 3/5, killed body 4/4, write flag 1/2, timeouts 0/2, liveness 1/1.

## Findings
- B1 HIGH, B2 MEDIUM: above; both block this head.
- F1 MEDIUM: Q5, Q6, Q8, objection 1: parametrise the id-encoding test over all seven verbs.
- F2 MEDIUM: U5, objection 2: add a `ReadTimeout` case; B1's test would also be that case.
- F3 LOW: T1, T2, W2, U4.

## Not verified
Rebase; CI; GX10; what the live service answers to `/` or `/kill` on a dot-segment retarget; that no other CLI (lifecycle-manager, spend-governor) has the same two defects (not read here).
