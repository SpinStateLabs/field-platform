VERDICT: PASS WITH CONDITIONS on 19365c571927d9d8884ccc41a7ae5e5921a9510d

Condition (one): my whole `python -m pytest -q tools/tests` run had NOT finished when this was written (about 48 percent, no failure so far). The PR touches nothing under tools/ or docs/. I will append the result as an addendum to this file; until then treat the tools suite as unrun by me. Everything else below is complete.

Card C-446, PR 288 (C-221, reviewer C-200 F-C200-4), Lane 7. Head confirmed with the PR read before and after the work: 19365c5, one commit, base 7e8f16e is main. Cherry-pick onto main 7e8f16e applies clean (no conflict, no rebuild needed). A PASS applies to this SHA only.

OBJECTIONS (before evaluation)
1. A guarded write could lose the pair: any of the seven writes (kill, revive, drill, bulk, fleet halt, token revoke, escalation resolve) that forgets `operator: true` now fails on the estate with 401 in ENFORCE mode, where before the blanket header hid the omission. Opt-in is the safer failure direction (a refused write, not a leaked key) but it is a regression risk.
2. A read could still carry the pair through a second path: three `fetch` calls bypass `api()` and call `hdrs()` directly (manifest, export, stream).
3. The setup area (`sfetch`) had its own strip loop; replacing it with a parameter could change what the setup POSTs send.
4. The one-line test pin changed from "named once" to "named zero times": a pin loosened or deleted to make the change fit would be a regression.
5. Redirect or cross-origin: custom headers survive a same-origin redirect and a browser sends them on a cross-origin redirect target for a guarded POST.

ASSUMPTIONS
A1. Tests read the shipped console.html (jsdom harness), so a mutant of the file is a mutant of the product (HIGH, read test_setup_behaviour.py).
A2. The seven guarded routes are the ones that call `_operator_kw` in services/ops-console/src/ops_console/api.py (:665, :670, :675, :683, :707, :739, :745) (HIGH, read).
A3. `/api/check` proxies to the sentinel with the perimeter secret alone (api.py:747-751), so it is not a guarded write (HIGH, read).

REASONING
1. Call-site census, `console.html` on the head: every `fetch` is in api() (:835), sfetch (:1464) or one of three direct calls (:1199 manifest, :1268 export, :1351 stream). Those three still call `hdrs()` with no argument, so `withOperator === true` is false and they carry the perimeter secret only (HIGH).
2. Writes: act() (:865) covers kill, revive, drill, revoke, resolve; bulk (:1100) and fleet halt (:1127) pass the flag themselves: 7 of 7 against the 7 `_operator_kw` routes. `/api/check` (:1322) correctly carries none (HIGH).
3. sfetch: the strip loop is replaced by `hdrs(withOp)` and has the same effect; the three setup writes already passed `operator: true` on main (:1671, :1694, :1720); the setup reads and `/sentinel/check` carry none, as before (HIGH).
4. Secure-context refusal intact: `keyTransportOk()` is still in the send condition (:783); the key_send_gate mutant was re-anchored and still goes red. The diff adds no new read of the key into the DOM, storage, a URL, a log or an error text (diff read, HIGH).
5. Test pin: 1 -> 0 occurrences is stricter (the setup script must no longer name the header), the OPKEY half of the assertion is unchanged (HIGH).
6. Redirect and cross-origin: all calls use relative paths; the server has no cross-origin redirect route on these paths. Not proven in a browser (LOW): see "What I did NOT do".

TESTS (own run, cherry-picked head on main 7e8f16e, Python 3.13, CI install set, constraints file)
- Whole ops-console suite: 236 passed, 0 skipped, 185 s. Matches the builder's 236.
- Whole `python -m pytest -q tools/tests`: started, not finished at the time of writing (about 48 percent, no failure seen). Result goes in an addendum.
- CI on the head at the time of writing: 6 of 7 success (tests 3.11, 3.12, 3.13, fly-image-smoke, compose-smoke, compose-upgrade-smoke); tests (3.14) was still running. The coordinator must confirm 7 of 7 on the exact head.

MUTANTS (hand, in console.html, whole behaviour and steps and escaping and identity files run for each): 13 red / 14.
M1 hdrs sends unconditionally, M3 api() drops the flag, M4 act drops it, M5 bulk drops it, M6 fleet halt drops it, M7 sfetch always sends, M8 setup register POST drops it, M9 `/api/check` sends the pair, M10 manifest read sends, M11 export read sends, M12 stream sends, M13 api() sends on every call: all RED, each by the named dashboard_headers, read_headers or key_https case.
Survivors and special cases:
- M14 (the `operator` key is not deleted before the options reach `fetch`): SURVIVES, EQUIVALENT in behaviour. `fetch` ignores an unknown init member; headers are unaffected. LOW cosmetic only; no card needed.
- M2 (`withOperator &&` instead of `withOperator === true &&`): red only because it moves the anchor that the mutant table needs (test_each_check_fails_against_its_own_mutant), not by behaviour. Behaviourally equivalent today because every caller passes a boolean; the `=== true` form is the safer spelling and is pinned only by the anchor. LOW note.

FINDINGS
- F-C446-1 LOW, test-fragility: the `=== true` strictness (M2) is held by an anchor string, not by a behavioural probe. A truthy non-boolean caller (for example a future `operator: "yes"`) would send the pair on a read-shaped call and no test would go red. services/ops-console/src/ops_console/static/console.html:783. Builder card optional: one scenario that calls `hdrs("yes")`.
- F-C446-2 LOW, class-next-door, not proven: a guarded POST that receives a cross-origin redirect would re-send custom headers in a browser. Not in this PR; the server has no such route today. Sourced reason: fetch spec behaviour, general knowledge (MEDIUM). Candidate hardening: `redirect: "error"` on the guarded writes.

CONCLUSION: PASS WITH CONDITIONS on 19365c571927d9d8884ccc41a7ae5e5921a9510d (the condition is only the unfinished tools-suite run). Seven of seven guarded writes carry the pair, every read, the stream, the export and the check carry the perimeter secret alone, the secure-context gate holds, and 13 of 14 mutants go red with the one survivor equivalent. The coordinator still needs GX10 16/0 (the builder did not run it) and CI 7/7 on this exact head.

What I did NOT do
- Not run on the GX10 (this cloud session has no GX10 tool); my runs were local on Python 3.13 only, not 3.11, 3.12 or 3.14.
- Not run in a real browser: the evidence is jsdom against a stub estate, so redirect, preflight and cross-origin behaviour are reasoned, not observed.
- Did not read the console.html changes of any later PR; did not look at the estate.
- CI was 6 of 7 when I last read it.

ADDENDUM (Lane 7, after the report above): tools suite and duplicate reviews
- Whole `python -m pytest -q tools/tests` on main 3ee2e5d plus the cherry-picked PR 288 commit (applies clean): 2806 passed, 7 skipped, 0 failed, 776 s (Python 3.13, CI install set). The condition in the verdict line is met; the verdict stands as PASS on 19365c571927d9d8884ccc41a7ae5e5921a9510d. The skips were not examined one by one; the listed reason on this host includes no PowerShell.
- C-446 was reviewed three times at this head (Lane 5, Lane 6 and this report). All three give PASS. My F-C446-2 (redirect on guarded writes) is the same finding as Lane 5 F-C446-2 and Lane 6 F-C446-1 (`redirect: "error"`); my F-C446-1 (truthiness spelling, anchor only) is not in the other two. Lane 5 F-C446-1 (`credentials: "same-origin"` unpinned in sfetch) I did not test: not in my report.
- My first tools run on this tree was contaminated (I switched the checkout under it) and was discarded; the numbers above are from a clean second run.
