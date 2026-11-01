VERDICT: AUDIT (no PR head, no merge gate) on main acaf5f241f: 0 HIGH, 1 MEDIUM, 3 MEDIUM-LOW, 1 LOW-MEDIUM, 6 LOW, 1 INFO. The fail-closed core of both services holds where it was mutated before; the new findings are in decision branches that default to pass on a value they do not recognise, and in validation of values read from a file or a peer service.

# C-1079 reviewer report (Lane 14, cloud, read audit): services/claude-approver and services/conformance-sentinel on main acaf5f24

UNVERIFIED: cloud run, no GX10, no mutants (the card says none). Code was read from a scratch worktree of main acaf5f24. Where a finding says PROBED, I ran the real code on made-up data in that worktree and restored nothing (nothing was edited). Where it says READ, I did not run it.

## OBJECTIONS FIRST

1. The card asks "does it fail closed". Four branches below do not: an unrecognised value ends in the pass path (F-S1, F-S2, F-S3) or the cursor guard is bypassed on the second tick (F-A1). A "fails closed" statement for either service needs those four qualifiers.
2. Both services were mutated before at older mains (C-156, C-157; main 70fa59f) and their fail-closed pins were added after (C-168, C-169, C-258, C-412, C-503). A survivor list at an older main says nothing about the branches that were added since; I read the current code and name the branches with no test below.
3. Failure conditions for "the Sentinel and the approver are sound": (a) a proxy or a governor release returns a decision or state spelling the code does not know and the caller proceeds (F-S1, F-S3); (b) a governor reply loses `spent_cents` and a token spend ceiling stops biting (F-S2); (c) a cursor file with one bad value disables the double-post guard (F-A1).
4. Steelman for the current code: both services sit behind the perimeter secret, the replies they parse come from services on the same estate, and the approver treats every unknown sentinel decision as deny (core.py:480-483). The findings are defence in depth, not a remote exploit. I do not claim otherwise.

## ASSUMPTIONS

A1 Main is acaf5f24 (fetched at review time, shallow clone; read with `git show` and a detached worktree).
A2 The perimeter (`x-field-auth`) is armed on the estate; on the approver `/halt` is exempt by design (api.py:10-16).
A3 Earlier reports cover what their own text says; I list them and did not repeat their mutants.
A4 A reply from the governor, registry, delegation-authority or sentinel is trusted for origin but not for shape.
A5 `FIELD_SENTINEL_MODE` is enforce for the claims about blocking; in log-only every verdict is ALLOW by design (mode.py:1-17).

## STEP 1: what earlier reports already covered (not repeated)

claude-approver:
- C-156 (70fa59f): `_check` read in full, 221 mutants (164 killed, 57 survived); findings F-C156-1 (an ALLOW authorizes a tool name; `irreversible` constant false), F-C156-2 (`/halt` header marker only), -3 to -6 (labels, halt session filter, config validation, core guards).
- C-59 triage, C-209 README, C-233 poller usage, C-272 pins, C-522 cursor re-audit (C-445 holds; far-future cursor F-C522-1, spellings F-C522-2; builder C-687 on PR 333).
- Builder pins since: C-163, C-257, C-258, C-412 (tests named test_approver_*).
conformance-sentinel:
- C-157 (70fa59f): decision order, 145 mutants (124 killed, 21 survived), untested irreversible forbid / allow_with_ledger, unrecognised mode.
- C-382 / C-377 mode message, C-169 unrecognised mode, C-168 fail-closed pins, C-503 no upstream body in error text (seeded.py and cli.py only), C-529 ADR 02 against the source (27 statements), C-543 PR 317 conformance rate.

## STEP 2: what I read (main acaf5f24)

claude-approver: api.py, client.py, cli.py, config.py in full; core.py lines 54-172, 223-304, 398-500, 504-672, 670-830, 828-994 (everything except the Estate/Verdict dataclasses at 182-222 and the constructor 317-397).
conformance-sentinel: api.py, mode.py, routing.py, governed.py, judge.py in full; engine.py 1-80, 129-378, 378-471, 472-641 (everything but the middle of `_decide` 560-592 read only through its early branches).
NOT read: measure.py, seeded.py, self_manifest.py, cli.py beyond its echo sites, the SPEC and README files, demo scripts, and the test bodies other than the ones named below.

## REASONING (per finding, with the test file I checked)

### claude-approver

F-C1079-A1 MEDIUM-LOW [PROBED, HIGH] usage cursor: `UsageCursor.load` (core.py:262-284) catches `(ValueError, TypeError)` only and sets `_loaded = True` before it parses (:265). A cursor file holding a non-finite number (`Infinity`, which Python's JSON reader accepts) raises `OverflowError` on the first load: `_tick` calls `self.cursor.load()` at core.py:536, before the session loop, so that tick answers no approval at all (`tick_errors` +1). The second tick's `load()` returns at once with `data == {}` and `error is None`, so `_post_usage` (core.py:849) runs with an empty cursor and would re-post every session's whole usage history: the guard documented at core.py:249-255 ("corrupt cursor disables usage posting rather than starting from zero") is bypassed. PROBED: first load raises OverflowError, second returns no error and no data; `NaN` is handled (error set). The same loader also accepts negative and boolean values (`-5` stored as -5, `true` as 1; core.py:282), and a negative cursor makes the next delta larger than the real usage (core.py:859). The cursor is written by this process only, so the trigger is a disk fault or a hand edit. Test checked: test_approver_usage.py (corrupt cursor via `cursor.error`; no Infinity or negative case; grep for `Infinity|OverflowError` over the test folder: none).
  Kill test: write `{"s":{"input_tokens":Infinity}}` as the cursor, tick twice, assert `cursor.error` is set and no usage post happens on either tick; and a cursor with `-5` is "corrupt".

F-C1079-A2 LOW [READ, HIGH] one bad session stops the tick: `_tick` wraps `sessions.list` in a try (core.py:543-549) but not `_approve_session` after `_read_events`, `_answer`, or `_post_usage`. `_usage_snapshot` keeps a value when `isinstance(v, (int, float)) and v >= 0` and then calls `int(v)` (core.py:841): an infinite float passes the guard and `int(inf)` raises OverflowError. The exception leaves `_tick`; `tick()` counts `tick_errors` (core.py:507-510) and every session after the bad one, for every later agent, is skipped that tick, and again each tick while the same session stays first. Safe direction (no false allow) but an availability coupling between sessions. Tests checked: test_approver_usage.py:75 asserts `tick_errors == 0` after a failed usage post; no test drives `tick_errors > 0`.
  Kill test: a first session whose `usage` is `float('inf')` and a second with an open ask; assert the second is answered in the same tick and `tick_errors` stays 0.

F-C1079-A3 LOW [READ, HIGH] unbounded growth: `self.custom_seen` (core.py:356, 640-641) is added to for every custom tool use and never pruned or reset; `SessionState.seen` grows with every event of a session until the session leaves the listing (core.py:565-568). The decision record keeps the raw `tool_name` (core.py:707, 722) in a 500-entry deque that `/stats` returns (api.py:58-60); the name has no length bound in this code (the API's own limit is not in this repo). Tests: `custom_seen` is not referenced by any approver test; `test_decisions_keep_the_last_500` bounds the count, not the size.
  Kill test: 10,000 distinct custom tool events across ticks leave `len(custom_seen)` under a stated bound; a 100 KB tool name appears truncated in `/stats`.

F-C1079-A4 LOW [READ, HIGH] untested guards: the `DENY_MESSAGE_MAX` cut (core.py:716-717; tests reference `deny_message` in test_approver_estate.py, test_approver_review_fixes.py, test_approver_tick.py but none asserts a length; grep for `1000|DENY_MESSAGE_MAX`: no hit in the assertions), and `REASON_MAX` has a test (test_approver_api.py:141-145, `reason[:512]`). A sentinel `reasons` list is joined without a bound before the cut (core.py:452, 460).
  Kill test: a sentinel BLOCK with a 5,000-character reason produces a `deny_message` of exactly 1,000 characters.

F-C1079-A5 INFO / design, carried from C-156 and unchanged on main [READ, HIGH]: (1) `irreversible` is a constant `False` and the sentinel sees the tool name only, so an ALLOW authorizes a name (core.py:379-386, F-C156-1). (2) `POST /halt/{id}` is exempt from the perimeter for every mapped id and checks one header marker (api.py:31-38, 62-70, F-C156-2; the README declares it). New observation: `halt` is a synchronous route that waits up to `CLAUDE_APPROVER_HALT_WAIT_SECONDS` (default 20, config.py:21) per session in the server's worker pool (core.py:937-951), so a burst of marker-only calls can hold the pool that also serves `/health` and `/stats`. A builder card may cap concurrent halts or answer 429; a Don decision whether the marker stays. Test checked: test_approver_api.py:112-200 (marker, 404, 503, interrupt, never archive a running session, per-session errors); no concurrency test.

### conformance-sentinel

F-C1079-S1 MEDIUM [PROBED, HIGH] `Governor.check` treats an unknown decision as pass: governed.py:102-106 refuses only the exact strings `BLOCK` and `ESCALATE` and returns the verdict for anything else, so the wrapped function runs. PROBED with a stub transport answering 200: `{"decision":"DENY"}`, `{"decision":"block"}`, `{"decision":""}` and `{"decision":null}` all RETURNED a verdict (the wrapped call would run); a body with no `decision` raised KeyError and a list raised TypeError (both stop the call by accident, outside the try). The approver's `_check` is the model to copy: it allows only an exact `ALLOW` and denies every other value (core.py:455-483). The real sentinel cannot emit these spellings (its model is an enum, field_core.conformance), so the exposure is a proxy or a version skew between the SDK-side `Governor` and the service. Also PROBED: governed.py:99 puts `{exc}` into the reason, and httpx's status-error text carries the request URL; with a sentinel URL that has userinfo the credential appears in the `ActionBlocked` message (probe string `pw`, made up). Tests checked: tests/conftest.py, test_sentinel.py, test_throttle_metering.py use `Governor`; grep for `DENY|unknown decision` over the sentinel tests: none.
  Kill test: a 200 reply whose decision is any string other than `ALLOW` raises `ActionBlocked`; and the blocked message never contains the userinfo of the sentinel URL.

F-C1079-S2 MEDIUM-LOW [PROBED, HIGH] token spend ceiling reads a missing total as zero: engine.py:461 `spent = int(totals.get("spent_cents", 0))`. PROBED on `_token_ceiling` with a USD reply: no `spent_cents` key -> ceiling passes (no verdict); `-5` -> passes; `true` -> passes (counts as 1); `null` -> TypeError; `"abc"` -> ValueError; `NaN` -> ValueError (each leaves `check`, so `/check` answers 500 with no ledgered verdict and no clause); `150` and the string `"150"` over a 100-cent ceiling -> BLOCK E.spend_cap. The docstring promises "an unverifiable total BLOCKs" (engine.py:420-422). Tests checked: test_fail_closed_pins_c168.py:97,108 and test_throttle_metering.py:545-674 use `spent_cents` 0 and numeric values only.
  Kill test: a governor `/totals` reply without `spent_cents` (and with `null`, a string, a negative) yields BLOCK E.spend_cap.

F-C1079-S3 MEDIUM-LOW [READ, HIGH; not run] spend `state` is a deny-list: engine.py:623-640 refuses `BLOCK`, `THROTTLED` and `ESCALATE` and falls through to ALLOW for every other value, including a missing `state` and a spelling a later governor release adds. The registry and the manifest paths before it fail closed on unknowns; this branch does not. Tests: test_throttle_metering.py covers the three named states.
  Kill test: a governor status whose `state` is an unknown string yields ESCALATE or BLOCK, not ALLOW (decide with Don whether OK is the only passing value).

F-C1079-S4 LOW-MEDIUM [READ plus the F-S1 probe, MEDIUM] transport text in verdict reasons: engine.py:272, 299, 320, 332, 432, 442, 494, 526 and 602 put `{exc}` (or `str(exc)[:300]`) into the reasons of a verdict that `/check` returns, the ledger records, and (through the approver) core.py:716-717 sends to the agent's own session as `deny_message`. Where `exc` is the repo's own `ConnectionError("governor returned 500")` the text is a status; where it is httpx's transport error the text carries the internal service URL (F-S1 probe shows httpx's own message includes the URL). C-503 pinned this for seeded.py and cli.py only (test_upstream_errors_c503.py:50-61 is a source check of those two files); engine.py is not in it. Test checked: test_f2_fail_closed.py:125-148 asserts the class name or the status appears in `reasons[1]`, not that a URL is absent.
  Kill test: a registry, delegation and governor stub that raises an error whose text holds a marker URL; assert the marker is absent from `reasons` for every `_decide` branch above.

F-C1079-S5 LOW [PROBED, HIGH] confidence floor config: `resolve_floor` (judge.py:200-205) clamps rather than refuses: `0` and `-1` give 0.0 (every judgment above zero confidence passes the floor), `80` (meant as a percent) gives 1.0 (strict), `nan` and `inf` give 1.0, an unparsable value gives the default 0.8. `resolve_mode` raises on a typo (mode.py:34-49); this one does not. Test checked: test_judge.py:67-70 (unset, 0.5).
  Kill test: `FIELD_JUDGE_CONFIDENCE_FLOOR` of `0` or a negative is refused (or is documented and pinned); decide the policy with Don.

F-C1079-S6 LOW, carried (C-883 / PR 371, still open at head 8eb5c87205 when read) [PROBED, HIGH]: `RegistryClient.get_agent` (field_core/clients.py:363) puts the caller's `agent_id` into the URL unquoted, and `CheckRequest.agent_id` has only `min_length=1` (engine.py:41). PROBED with a made-up id: a value with dot segments left the `/agents/` prefix and the request went to another path of the registry (the answer then fails the status check); a `?` or `#` truncated the path; a space was encoded. GET only, behind the perimeter, with the sentinel's own identity headers. Sentinel `/check` is a reach path the PR 371 tests should include. No recipe is given beyond the class.
  Kill test: `/check` with an `agent_id` containing a path or query delimiter answers 422 (or BLOCK R.unregistered) and no stub request leaves `/agents/<one segment>`.

F-C1079-S7 LOW [READ, HIGH] no size bound on the request: `CheckRequest.action` and `context` have no maximum (engine.py:39-50). `MAX_ACTION_CHARS = 500` exists only inside the judge's injection screen (judge.py:35, 60), which runs only when the judge is on and the routing predicate fires. The action is copied into the verdict, the ledger payload (engine.py:202, 267) and the shadow record. Test: none for a large action.
  Kill test: a 1 MB `action` answers 422 or is truncated in the ledger payload.

## CONCLUSION

1. Neither service has a HIGH finding on main acaf5f24 by this read; the allow path of the approver remains one function (`_check`, core.py:427) and the sentinel's identity, token and scope steps fail closed.
2. The branches to fix first are the pass-by-default ones: F-S1 (governed.py), F-S2 and F-S3 (engine.py), then the cursor guard F-A1. All four have a one-line killing test above and are builder cards, not code here.
3. F-A5 (marker-only `/halt`) and F-S5 (floor policy) need a Don decision, not a builder.
4. Nothing was run that mutates a file; the probe scripts were made-up data against a detached worktree of main.

## NOT VERIFIED

- Any estate behaviour, any real API reply shape (the SDK models are typed, so F-A2's infinite value and F-A1's file value come from a fault, not from a normal reply).
- engine.py 560-592, measure.py, seeded.py, self_manifest.py, the SPEC and README files, cli.py beyond its echo sites.
- That the cited test files contain no other test that covers a finding: I grepped by name and by the values named, and read only the tests cited.
