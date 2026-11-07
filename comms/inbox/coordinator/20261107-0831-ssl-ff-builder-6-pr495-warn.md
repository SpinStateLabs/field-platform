# B-PR495-warn-and-health report (ssl-ff-builder-6)

PR 495 (fix/gateway-hygiene-env-guard-sb2): new head fe849b75001d0db3117beee2089c21dd9c564bae (pushed, verified against ls-remote). Main merged in without conflicts; no force push. PR 866 not touched.

Built per the architect ruling:
- `_env_int` / `_env_float` take an optional `fallbacks` set. A SET, unusable value (junk, NaN, inf, out of range) still gives the default, and now logs one WARNING per process per variable ("<NAME> is not usable (accepted: <range>); the default is in effect"). The value is never in the message.
- `create_app` collects the names (sorted, names only) into `app.state.env_fallbacks`, served as `env_fallbacks` in the gateway /health.
- Unset or valid: no warning, empty list. A BLANK variable is treated as unset (no warning) because compose passes blanks; say if blank should count as junk.
- Explicit create_app arguments still win and do not warn or list.
- Five docs/ENVIRONMENT.md rows: "nothing is logged" replaced with the warning and field; environment_anchors --fix then --check: 0 wrong rows.
- A19: test_an_explicit_latency_budget_wins... already asserted == 5.0; the new test also pins it with the cooldown.

Tests (tests/test_env_fallback_warning_pr495.py): 5 settings x 8 bad values each give default + exactly one warning naming the variable + env_fallbacks entry (also in /health); over-ceiling values per setting; sentinel string and a large number appear in no log line, /health body, exception text or env_fallbacks; warning carries a range; sorted names; unset/valid/blank clean; one per process across apps and requests; one per variable; explicit argument wins. Local: that file plus test_hygiene_env_guard_sb2.py 133 passed, 1 skipped (Windows).
Mutants (7, one at a time, committed first, source restored): warning dropped, value echoed, env_fallbacks emptied, warn per call, valid int warns, valid float warns, unsorted names: all 7 KILLED.

NOT done / not verified: CI on the new head has not run yet (check `gh pr checks 495`); the GX10 run on the exact head is not done by me (I do not run against the estate host): needs another session. Don-only items unchanged (ceilings, cooldown 0 as built).
