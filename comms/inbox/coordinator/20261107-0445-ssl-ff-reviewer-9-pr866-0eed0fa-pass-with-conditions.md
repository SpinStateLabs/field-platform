VERDICT: PASS WITH CONDITIONS on 0eed0fa04ad2417c2670dfa0ef51274ad61a58ed  (ssl-ff-reviewer-9; Windows, Python 3.14.2, no GX10, CI not read). The change does what it says: the five numeric gateway tunables are refused at start by name and range (never the value), now with ceilings, and a configured sentinel URL is shown only as scheme, host and port. One real overlap problem for the coordinator: PR 866, PR 789 and PR 495 edit the same lines and 495 takes the opposite policy. The standing gate stays open.

R-PR866-0eed0fa, PR 866 (force-gateway: numeric tunables and the sentinel URL never echo a value; rebuild of #352). Applies to this head only. The fetched pull/866/head is 0eed0fa0: 7 commits over main, 0 behind, `git merge-tree` clean. Against main: api.py about +88, docs/ENVIRONMENT.md about +26, a new test file (262 lines). Nothing under .github/. Identity: 7 of 7 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only, none Fable.

OBJECTIONS FIRST
1. POLICY CONFLICT across open PRs, measured with `git merge-tree`: 866 conflicts with PR 789 and with PR 495 in api.py and docs/ENVIRONMENT.md. 789 (PASSed by me on 4d5241dd) refuses the same five tunables at start but treats a blank value as the default and gives only the cooldown a ceiling; 866 refuses with ceilings 1000 / 100 / 60,000 ms / 10,000 and refuses a blank value; 495 ("junk settings fall back to defaults") takes the OPPOSITE policy (silent fallback). Only one policy can land; whichever lands second needs a hand merge. The PR body names the 495 overlap but not 789. MEDIUM operationally. HIGH (measured).
2. Mutant E2 (the RANGE refusal message also printing the value) SURVIVES the 95 tests: the PR's claim is "never the value", and the test accepts the value when it is "0" or "1" (test line 232) and does not pin the range path with another number. The unmutated code does not echo (measured). The value there has already parsed as a number, so it carries no secret: LOW, but it is the one pinned claim that is half-pinned. HIGH.
3. A blank variable (set but empty) is now refused ("is not an integer"); on main int("") raised too (a crash), so it is not a regression, but PR 789 reads blank as the default; a compose file with an empty substitution would stop the gateway under 866 and not under 789. LOW. HIGH (measured).
4. Parsing quirks remain: "1_0" reads as 10, "+5" as 5, Arabic-Indic digits as their value, " 7 " as 7; "5.0", "1e3", "0x10", "nan" for an integer setting are refused. LOW.
5. The latency budget has a ceiling but no useful floor: 0.0001 and 1e-300 are accepted (the bypass trips on every request). This is my condition C2 on PR 789 and is not closed here. LOW-MEDIUM. HIGH (measured).
6. public_origin refuses a non-ASCII hostname: a legitimate IDN shows as the fixed word "(unparsable url)" in /health. Safe, but misleading; the xn-- form works. LOW.
7. /health now shows the sentinel URL as an origin. CI's own smoke check (ci.yml line 211, sentinel_url equals the compose sentinel origin) still holds: public_origin of that exact origin returns it unchanged (measured). A URL with a path or credentials would now read differently; I found no other consumer of the key in the repo (grep of main). LOW. MEDIUM.

ASSUMPTIONS
A1 Probes call `_env_number` and `public_origin` directly (the PR's own helpers), as `create_app` does. A2 "Value echoed" means the configured string, or a number parsed from it, in a message.

REASONING / CHECKS
1. Diff read: `_env_number(name, default, cast, low, high, low_open, high_open)` refuses a ValueError (raised outside the handler, so no chained text), a non-finite float and out-of-range values, naming the variable and range; ceilings MAX_HYGIENE_WINDOW 1000, MAX_BASELINE_WINDOWS 100, MAX_LATENCY_BUDGET_MS 60,000, MAX_BYPASS_COOLDOWN 10,000; band in (0, 1) open; budget above 0; `public_origin` keeps scheme (http or https), host and port, drops userinfo, path, query, fragment, and shows a fixed word for anything unparsable; `_is_host` refuses a scope id; the SentinelUnavailable text uses the origin and the exception type name, raised outside the handler. HIGH.
2. Direct probes on this head: window 1 to 1000 accepted; 1001, 0, -1, a 5,000-digit string and "nan" refused; band 0.9999999 accepted; 0, 1, nan, inf, -0.0, 1e999 refused; latency 60000 accepted; 60000.0001, 1e300, 0, -5, nan refused; cooldown 0 and 10000 accepted, 10001 and -1 refused; a secret-looking value gives "is not an integer" with no value; `public_origin` strips userinfo, path, query and fragment, refuses ftp, a bad port, spaces, an override character, a scope id and a bare secret-looking string, accepts an IPv6 literal and underscore hosts. HIGH (measured).
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1): tests/test_no_value_echo_c582, test_422_no_echo_force_gateway_c1114, test_f1_flags, test_posture_flags_c180, test_d2_drift_dimensions = 333 passed; tools/tests test_environment_doc, test_boundary_echo_lint_c505, test_boundary_echo_blindspots_c1117, test_environment_anchors_c1116 = 195 passed; `environment_anchors.py --check` 0 wrong rows. The whole force-gateway suite was not run. HIGH on what ran.
4. Mutants on a temp copy of the head, api.py, the PR's new test file only (-x, a kill = pytest rc 1):

| group | mutations | result |
|-------|-----------|--------|
| echo | not-a-number message echoes value (E1); transport error chained (T1); transport message carries the raw URL (T2); numeric ValueError chained (V1) | 4 KILLED |
| echo | range message echoes value (E2) | SURVIVED (objection 2) |
| bounds | non-finite accepted; low ignored; low open ignored; high ignored; high open ignored; high off by one (E3 to E8) | 6 KILLED |
| ceilings | window 1e9, baseline 1e9, latency 1e300, cooldown 1e9, window 1001 (W1 to W5) | 5 KILLED |
| per setting | band upper removed, band low open off, band high open off, latency low open off, cooldown low -1, cooldown low 1, window low 0, baseline low 0 (B1 to B3, L1, K1, K2, H1, H2) | 8 KILLED |
| origin | keeps userinfo, keeps path, scheme unchecked, host unchecked, scope id allowed, unparsable echoes url, junk host echoes url, hostname regex any char, IP literal refused, /health shows raw url (O1 to O10) | 10 KILLED |

Counted: 34 run, 33 KILLED, 1 SURVIVED (E2), 0 NOT APPLIED. HIGH.

CONDITIONS
C1 (decision for the coordinator, before landing) choose ONE tunable policy among 866 (refuse with ceilings), 789 (refuse, blank = default, cooldown ceiling) and 495 (fall back to defaults); close the losers or rebase them on the winner; the five ENVIRONMENT.md rows must be reconciled by hand.
C2 (non-blocking, a condition fix) pin E2: assert a range-refused number does not appear in the message for values not in the range text (for example 10001 and 61000).
C3 (non-blocking, new PR) a floor above 0 for the latency budget; blank-as-default if 789's rule wins; IDN hosts shown as punycode.
C4 (standing gate) GX10 16/16 and CI on this exact head; not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
The whole force-gateway suite, GX10 / Linux, CI, a running gateway start with a bad value.

CONCLUSION
The merge is clean and the code matches its claims: 33 of 34 mutants die, all probes agree, identity correct, 333 plus 195 tests pass and the anchors are green. The only test gap is the range-message echo (E2, a number that has already parsed). The real issue is organisational: three open PRs rewrite the same lines with two incompatible policies. PASS WITH CONDITIONS on 0eed0fa0: C1 decision, C2 and C3 non-blocking, C4 the gate.
