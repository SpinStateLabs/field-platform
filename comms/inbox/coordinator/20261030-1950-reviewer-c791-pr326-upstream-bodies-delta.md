VERDICT: FAIL on da33a9a1541e65010ac6ef53d075040b0b3fdd65  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-791, PR 326 after C-729 (PASS WITH CONDITIONS). The card asks: each C-729 condition, whether da33a9a closes it, any raise or log site still carrying a body. Answer: none of the three C-729 conditions is closed at this head, and at least six sites still carry a body. This SHA only.

OBJECTIONS FIRST
1. An unusable SUCCESS reply still hands the body to the caller (C-729 F-C729-1, open). Probe (httpx MockTransport, marker in the body; scan of message, repr, args and attributes down the __cause__/__context__ chain, and the formatted traceback):
   - liveness.py:70 (heartbeat 200): wrong-shape object, JSON list, JSON string: pydantic ValidationError with the body in message and traceback; malformed JSON: JSONDecodeError with the body on `.doc`. (PR 372's head 90881a5 fixes this site; this head does not.)
   - usage.py:113 report and usage.py:144 spend, 201: same two classes of leak.
   - bootstrap.py:94 mint, 201: ValidationError leak; malformed JSON: `.doc` leak. bootstrap.py:60 register, 201: malformed JSON `.doc` leak; a wrong-shape body or a list returns without any error.
   - federation.py:157 cross, 200 with malformed JSON: CrossingBlocked is raised but the body stays reachable on the chained JSONDecodeError `.doc` (__context__); wrong shape and list: clean.
   Confidence HIGH (observed). I also found the same class at the 201 sites on PR 372 (report C-785), which fixed heartbeat and federation only.
2. The sentinel CLI `check` verb (conformance_sentinel/cli.py:49) still prints `error <status>: <body>`. Probe: CliRunner `check a act` with the HTTP call returning 500 and 403 carrying a marker body: exit 1, the marker is in the output for both. C-729 reported the sentinel /check sites clean; that was the score path (cli.py:151, now upstream_error) and seeded.py, not this verb. PR 372 fixes this line. Confidence HIGH.
3. Other raise and echo sites outside this PR (C-729 F-C729-2, open): field-core clients.py:307, :322, :339, :373, :398, :430 call resp.json() unguarded (not probed individually: a malformed success body there raises the library error with the body on `.doc`; MEDIUM); sentinel api.py:45, governed.py:95, judge.py:163 and engine.py:90,114,148 parse bodies; cli.py:94,140-141,153 likewise. I did not run these.
4. Branch state: not mergeable as is. `git merge-tree` against origin/main reports add/add conflicts in packages/field-core/tests/test_upstream_error_c503.py and services/conformance-sentinel/tests/test_upstream_errors_c503.py, as C-729 said (drop 203810f). Confidence HIGH.
5. BODY_LOG_LIMIT boundary (C-729): the test file asserts the constant is 200 (test_upstream_error_c503.py:155) and "fewer than the limit" lines (:97-98); I saw no test of a body of exactly the limit and limit plus one. Confidence MEDIUM (grep only).

ASSUMPTIONS
A1 The C-729 conditions are those in its PROPOSED CARD paragraph (wrap model_validate(resp.json()); pin list and string bodies; rebase and drop 203810f; pin BODY_LOG_LIMIT at its boundary; separate card for lifecycle-manager engine detail and field-core transport messages). A2 "Carries a body" = marker in message, repr, args, attributes of any exception in the chain, or in output.

REASONING / CHECKS
- Probe matrix at this head: bodies malformed JSON, wrong-shape object, JSON list, JSON string; statuses 200 and 201 on usage, heartbeat, register, mint, cross; 404 and 500 on usage, heartbeat, cross. Failure statuses (404, 500, and the non-201 usage 200): no leak on any site. Success statuses: leaks as listed in objection 1.
- Tests at this head: field-agent 168 passed; field-core test_upstream_error_c503 17 passed; conformance-sentinel 259 passed. The tests pin only the failure-status sites, which is why the success-status paths stand.
- Mutants: not re-run (C-729 reports 17 of 17 site mutants killed; I did not verify that count).
- Condition status: (a) wrap model_validate(resp.json()) at four SDK sites: OPEN. (b) list and string pins with the marker probe: OPEN (not in the test file; the probe shows the leak). (c) rebase dropping 203810f: OPEN (conflicts). (d) BODY_LOG_LIMIT boundary: OPEN (MEDIUM). (e) separate card for the lifecycle-manager engine and field-core transport messages: not in this PR; not probed.
- Commits: 2 (203810f, da33a9a), author and committer Don Hagell no-reply. Diff scan: no address, flag value, credential or deploy status.

CONDITIONS
C1 (blocking) Take the success-status fixes from PR 372's pattern (record the type name inside the except, raise the SDK error outside the block) at liveness.py:70, usage.py:113, :144, bootstrap.py:60, :94, federation.py:157; pin each with the marker probe including the chain.
C2 (blocking) Fix the sentinel `check` verb (cli.py:49) and pin it.
C3 (blocking for merge) Rebase onto main, dropping 203810f.
C4 (non-blocking) Boundary test for BODY_LOG_LIMIT; card the field-core client success parses and the sentinel parse sites.
C5 (coordinator) PR 326 and PR 372 overlap (372 covers the same field-agent files with a smaller diff); decide which carries the change.

NOT VERIFIED
GX10 full set, CI by run id, the field-core client success paths in practice, mutants, the lifecycle-manager engine sites, logging output (the DEBUG record is by design).

CONCLUSION
The failure-status messages are clean and pinned. The success-status paths and the sentinel check verb still carry the body, and none of C-729's conditions is closed. FAIL on da33a9a, UNVERIFIED.
