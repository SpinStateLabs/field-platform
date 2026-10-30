VERDICT: PASS WITH CONDITIONS on dcff705136a1f69e27b74631dbdd011a8e2ca591 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the two PR test files ran: 15 passed; the rest of the field-agent suite was not run)

Head matches the card. One commit on main; author and committer are the no-reply identity. Files: packages/field-agent/src/field_agent/canary.py (+10 -4 net), tests/test_canary_response_cap_c106.py (+131), tests/test_field_client_proxy_c53.py (+29 -?).

OBJECTIONS FIRST
1. "Does any read path stay unbounded?" YES. The canary's heartbeat poll goes through field_agent/liveness.py, not through the bounded urllib_call: LivenessClient uses an httpx client and parses the reply with resp.json(), so a large kill-switch reply is read whole (liveness.py:59-70 area), and a non-200 reply puts the WHOLE body text into the exception message ("heartbeat returned N ... halting: " plus resp.text). That is both an unbounded read and an upstream-body echo into an error text (the class of cards C-503/C-504). PROVEN by reading; not probed against a live listener. The cap in this PR therefore bounds the canary's platform calls only; it does not bound the heartbeat. MEDIUM-LOW (the kill-switch is a trusted peer, but this is the path that decides halt).
2. A reply over the cap now returns status 200 with a dict {"response_too_large": 65536}: callers that test only the status see a 200. The two callers I checked treat a missing expected key as failure (the verify step requires hb.get("killed") is False, canary.py:440-441); the heartbeat path does not use this function. No fail-open found, but the contract "status 200 plus a marker dict" is a new shape every future caller must handle. LOW.
3. The cap bounds BYTES READ, not time: a server that sends one byte every few seconds under a per-operation timeout is not bounded by this PR (the urllib timeout is per socket operation, not total). LOW; not a size issue.
4. The HTTPError branch reads with the bound but the error object is never closed (the PR's FieldClient twin closes it, field_client.py:165-167); a handful of unclosed error responses leak sockets until collected. LOW.
5. Tests: the PR's tests are an end-to-end listener test and unit pins; see mutants. No test for the heartbeat path (objection 1).

ASSUMPTIONS
A1 "Read path" = any place the agent package reads a network reply or an inbound request body. A2 Probes used local socket listeners; both FieldClient._call and canary.urllib_call were called directly. A3 One interpreter.

REASONING
1. Probe table (canary.urllib_call | FieldClient._call, 64 KiB = 65536 bytes): body of exactly the cap, valid JSON: parsed in both; one byte over the cap by Content-Length: canary returns {"response_too_large": 65536}, FieldClient returns no body; a Content-Length that LIES (declares one billion, sends ~66 KB then closes): both bounded (the read stops at cap+1); a chunked body of about 200 KiB: both bounded; a close-delimited body with no Content-Length (500 KiB): both bounded; an HTTP 500 carrying a 256 KiB body: canary (500, too-large marker), FieldClient (500, no body). All six returned in under a second; no memory growth beyond the cap by design. HIGH.
2. Inbound: the canary's own HTTP handler reads a request body only up to MAX_BODY_BYTES (canary.py:79, :194) and refuses chunked/transfer-encoded bodies (canary.py:184-187). HIGH.
3. FieldClient twin: field_client.py:161-164 reads cap+1 and drops an oversize body so every rule fails closed. HIGH.
4. Mutants (each alone, restored, worktree removed, nothing committed): canary read of exactly the cap instead of cap+1 -> 3 failed; ">" to ">=" -> 1 failed; HTTPError read unbounded -> 1 failed; success read unbounded -> 1 failed; cap doubled -> 1 failed; oversize returns a parsed prefix instead of the marker -> 3 failed; FieldClient ">" to ">=" -> 1 failed; FieldClient read unbounded -> 1 failed. All red. HIGH.
5. Liveness path: read, not run: the response handling at liveness.py (the non-200 branch builds its message from resp.text; the 200 branch validates resp.json() into the Heartbeat model). MEDIUM (no probe).
6. Diff scan: no address, SHA, flag value, deploy status or credential. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The cap on the canary's platform calls and the FieldClient pin are correct and well tested. The class "unbounded read" is not closed for the agent package because the heartbeat client reads and echoes a full reply. Conditions, none blocking:
- C1 F-C704-1: bound the heartbeat client's read and stop echoing the body in its error text; or open a card and name the path in the C-106 follow-up list.
- C2 F-C704-2: document the "response_too_large" marker shape where urllib_call is described.
- C3 F-C704-3: close the HTTPError in the canary's call (as FieldClient does).

FINDINGS
F-C704-1 MEDIUM-LOW, packages/field-agent/src/field_agent/liveness.py (the heartbeat _call: resp.json() unbounded; resp.text in the exception message). MEDIUM (read, not probed).
F-C704-2 LOW, packages/field-agent/src/field_agent/canary.py:366-367 (new 200-plus-marker shape). HIGH.
F-C704-3 LOW, canary.py:362-363 (HTTPError not closed). HIGH.
F-C704-4 LOW, canary.py:358-363 (bounded bytes, not bounded time). MEDIUM.

NOT VERIFIED: the heartbeat path against a live oversize reply; CI; the rest of the field-agent suite; behaviour of non-urllib clients elsewhere in the repository.
