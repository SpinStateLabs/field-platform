VERDICT: FAIL on 90881a5929f6e4bceb31a29a6adceff6b2c8492b  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-785, PR 372 (field-agent SDK errors carry no upstream body, C-642/C-729). The card's own scope includes "a 200 with malformed JSON, non-UTF-8 bytes, an oversize body" and "does any exception text, repr or attribute carry the body". At this head the success-status (201) paths of usage and bootstrap still do. This SHA only.

OBJECTIONS FIRST
1. Four raise sites still carry the upstream body on an unusable SUCCESS reply. Probe (httpx MockTransport, marker string in the body, scan of str, repr, args and __dict__ down the __cause__/__context__ chain, plus the formatted traceback):
   - usage.py:113 UsageClient.report and usage.py:144 UsageClient.spend, 201 with malformed JSON: raw JSONDecodeError, body on its `.doc` attribute; 201 with a JSON object of the wrong shape or a JSON list: pydantic ValidationError whose message, repr and formatted traceback contain the body.
   - bootstrap.py:94 mint, 201 with wrong shape or list: ValidationError, body in message and traceback; 201 with malformed JSON: JSONDecodeError `.doc` holds the body.
   - bootstrap.py:60 register, 201 with malformed JSON: JSONDecodeError `.doc` holds the body; a 201 with a wrong-shape object or a list returns without error (no validation at all, `return resp.json()`).
   The PR fixed this shape only for the heartbeat 200 and the federation 200 (liveness.py:69-76, federation.py:164-175). The same class of defect was left in the sibling modules. Confidence HIGH (observed).
2. Exception type contract: on those 201 cases the caller gets a library exception (JSONDecodeError, ValidationError) instead of UsageReportError or BootstrapError. UsageClient docstring says failures raise the SDK error ("Same strict rules as report: failure raises"), so a caller catching UsageReportError to fail closed will not catch it. Confidence HIGH.
3. A BLOCK verdict relays the broker's words (federation.py, the `_bounded(...)` call) and the whole verdict stays on `CrossingBlocked.verdict`. Documented as intentional in the PR comment; bounded to 300 characters, escaped via ascii(). It is upstream text in an exception message, which the C-503 rule says to avoid; this is a recorded exception, not an accident. Confidence HIGH on behaviour; a ruling, not a defect.
4. Oversize: nothing caps the read. A 3 MB body was read in full by the client on every path before any decision (httpx buffers it); the error text stays small, memory does not. Not new in this PR. Confidence HIGH.
5. Transport errors: `f"... unreachable: {exc}"` (usage.py:106,138; liveness.py:64; bootstrap.py:57,91; federation.py:156) include the httpx exception text. I did not find a body in a transport error; they can carry the URL. Unchanged by this PR. Confidence MEDIUM.

ASSUMPTIONS
A1 "Body" = any response bytes from the peer. A2 The marker scan over str/repr/args/__dict__ and the formatted traceback is a fair proxy for "text, repr or attribute". A3 The C-503 helper on main is the model: upstream_error(resp, what) returns "<what> returned <status>" only (field_core/errors.py).

REASONING / CHECKS
- Probe matrix (5 body kinds: malformed JSON, non-UTF-8 bytes, wrong-shape object, JSON list, 3 MB body; statuses 200 and 201; 404, 500, 403 with a marker body): 
  * non-success statuses on usage, heartbeat, federation, bootstrap: no leak anywhere (message, chain, attributes).
  * heartbeat 200 and federation 200, every body kind: HeartbeatUnreachable / CrossingBlocked, chain is the single exception, no leak. The raise outside the except block is what removes __context__ (my chain shows one link).
  * usage 200 (non-201): UsageReportError, no leak (this is the "not 201" branch).
  * usage 201, bootstrap 201: leaks as listed in objection 1. For non-UTF-8 bodies the JSONDecodeError/StopIteration carries no marker, so that case is clean.
- upstream_error change: the status is formatted only when it is a real int (bool excluded); otherwise "None". 
- Tests: field-agent 179 passed; field-core test_upstream_error_c503 17 passed; conformance-sentinel test_upstream_errors_c503 4 passed (run per package; one combined invocation fails collection on duplicate `tests` package names, which is a harness limit, not a code finding).
- Mutants (each restored, nothing committed): int guard removed KILLED (field-core test); bounded() truncation removed KILLED; ascii() escaping removed KILLED; heartbeat message adds resp.text KILLED; usage 404 relays resp.text KILLED; conformance-sentinel CLI back to resp.text KILLED; federation raise-inside-except KILLED. Seven of seven. The new tests do not cover the usage/bootstrap 201 paths, which is why objection 1 got through.
- Commit: 1 commit, author and committer Don Hagell no-reply. Diff scan: no address, flag value, credential or deploy status.

CONDITIONS
C1 (blocking) Apply the heartbeat pattern at usage.py:113, usage.py:144, bootstrap.py:60, bootstrap.py:94: validate inside a try, record type(exc).__name__, raise the SDK error outside the block, and add a test per site with a marker body that also scans the chain and attributes.
C2 (blocking with C1) bootstrap.register should validate its 201 reply or the card should say it is out of scope.
C3 (non-blocking) Don to rule whether the BLOCK reasons relay stays; if it does, say so in the C-503 note.
C4 (non-blocking) Cap the response read size in the SDK transport.

NOT VERIFIED
GX10 full set, CI by run id, any caller code in services that catches these exceptions, behaviour with real httpx transport errors, the CLI paths in field_agent/cli.py (they print `{exc}`; they inherit objection 1).

CONCLUSION
The heartbeat and federation sites are fixed and well tested. Four sibling sites on the 201 success path still hand the body to the caller through the exception text or attribute, so the card's question answers "yes" at this head. FAIL on 90881a5, UNVERIFIED; fix C1/C2 and re-review.
