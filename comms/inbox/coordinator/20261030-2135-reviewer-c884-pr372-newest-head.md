VERDICT: PASS WITH CONDITIONS on 1b8f9e3f7d453e95848b6a3cae0a271223421410  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-884, PR 372 (field-agent SDK errors carry no upstream body) after my C-785 and C-855. The head moved one commit since C-855 (b069869): 1b8f9e3 ("register's 201 reply is documented as returned as received; its failure message ..."), +29 -3 over three files (bootstrap.py docstring and message, a test, docs/ENVIRONMENT.md). This SHA only.

OBJECTIONS FIRST
1. No condition from C-785 or C-855 is open as a blocker. Re-run of the whole body-leak probe on this head: 116 cases (usage report and spend at 200 and 201, heartbeat, checkin, register at 201, mint at 201, crossing at 200, each with malformed JSON, non-UTF-8 bytes, a wrong-shape object, a JSON list, a JSON string, an empty body, JSON null, a number and a 3 MB body; plus 302, 400, 403, 404, 409, 500 and 502 on usage, mint, register, heartbeat and crossing), scanning message, repr, args, attributes and every link of the __cause__/__context__ chain and the formatted traceback for a marker: 0 leaks. The only case that returns without raising is `register` with a wrong-shape JSON object, which is now documented as intended ("returned AS RECEIVED: it must be a JSON object, but its fields are not validated here"); empty, null, number, list, string and malformed bodies all raise BootstrapError naming only the kind of failure. This closes C-855 C1 by documentation, as the builder chose. Confidence HIGH (observed).
2. The C-503 helper comparison (card ask): `field_core.errors.upstream_error` on main returns `"<what> returned <status>"` and writes the body only to a DEBUG log record, truncated to 200 characters and escaped. PR 372 adds one line: the status is formatted only when it is a real int (bool excluded), else "None", so an object whose `status_code` is text cannot carry a body through the message (errors.py, the added two lines). The field-agent and sentinel sites call the helper; the C-785 sites (usage, bootstrap) now follow the same "type name only" pattern. The SDK transport-error paths still format `{exc}` into the message (usage.py, liveness.py, bootstrap.py, federation.py `unreachable` lines); httpx transport exceptions carry no response body, but can carry a URL or host text (carried C-785 objection 5; not probed again). Confidence HIGH for the helper, MEDIUM for the transport text.
3. Carried and unchanged (not blockers): the BLOCK-reason relay on a crossing verdict (federation.py, bounded to 300 escaped characters, `.verdict` keeps the verdict) awaits Don's ruling; the SDK reads whole bodies with no size cap (a 3 MB reply is read in full on every path before any decision, though the error text stays fixed); PR 326 still overlaps these files and still leaks at its own head (C-791). Confidence HIGH.
4. Tests at this head: field-agent 204 passed, 1 skipped; field-core test_upstream_error_c503.py 17 passed. Commits: all author and committer Don Hagell no-reply; no address, flag value, credential or deploy status in the diff of src, tests or the docs cell.

ASSUMPTIONS
A1 Card scope: each condition at file:line against the head; 200 with malformed JSON, non-UTF-8 bytes, oversize body; compare with the C-503 helper. A2 The C-855 mutant results (7 of 9 killed; two survivors an equivalent and a pin gap) stand for the unchanged code; I did not re-run them.

REASONING / CHECKS
- Diff b069869 to 1b8f9e3 read in full; probe as in objection 1.
- Condition status: C-785 C1 closed (C-855), C2 closed by the documented contract, C3 open (ruling), C4 open (size cap).

CONDITIONS
C1 (non-blocking) Pin the type-name-only message in register (assert the text has no library detail), as in C-855 C2.
C2 (carried) Ruling on the BLOCK relay; a size cap on reads in the SDK transport.
C3 (coordinator, carried) PR 326 versus PR 372: close 326 once 372 lands.

NOT VERIFIED
GX10 full set, CI by run id, the CLI paths, real transport error text, field-core client success parses.

CONCLUSION
The head holds: 0 of 116 probe cases leak, the C-503 helper is applied at every status path, and the one remaining non-error case is a documented contract. PASS WITH CONDITIONS, none blocking. UNVERIFIED.
