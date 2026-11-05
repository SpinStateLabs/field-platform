# Review PR #770 (lifecycle-manager FIELD_LIFECYCLE_EVERY ASCII-digit parse, S8-13) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `d17442bd61377f2d93811796e2559c067570153c` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 4 files: lifecycle_manager/api.py (+23/-2), tests/test_every_env_parse_s8.py (+87), services/lifecycle-manager/README.md, docs/ENVIRONMENT.md. Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Behaviour: `_every_from_env()` = blank OFF silently; `re.fullmatch("[0-9]{1,9}")` is the interval; anything else OFF with a WARNING naming the variable, never the value. `create_app` also turns an explicit `every` above 999,999,999 into OFF with a warning. The `str.isdigit()` crash on `²` is real Python behaviour (the PR's own test asserts it). No floor (deliberate, disclosed; soak and tests use small values).
- Only adds refusals/diagnostics; no path became more permissive. The CLI path (typer int) is unchanged apart from the bound.
- tests/test_every_env_parse_s8.py: 31 passed on the head. `tools/environment_anchors.py --check`: 0 wrong anchors. The rest of the lifecycle suite: my run hit my 110 s limit before printing a summary (dots only, no failures seen); not verified to completion (LOW confidence on the PR's "300 passed").

## Mutants (api.py, one at a time, file restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | regex bound {1,9} to {1,10} | RED |
| M2 | fullmatch to match | RED |
| M3 | `[0-9]` to `\d` (Unicode digits) | RED |
| M4 | env-path warning removed | RED |
| M5 | explicit bound `>` to `>=` | RED |
| M6 | explicit-value bound check disabled | RED |
| M7 | warning echoes the raw value | RED |
| M8 | `.strip()` removed | RED |
| M9 | blank value warns | RED |
| M10 | MAX_EVERY_SECONDS constant raised | RED |
| M11 | explicit `every` branch rewritten to a no-op equivalent | no change (equivalent mutant, not counted) |
Totals counted from the table: 10 real mutants, 10 RED, 0 SURVIVED; 1 equivalent excluded.

## LOWs (optional, new PR)
1. README cites in the edited section are stale after the +17 lines in api.py: `api.py:376-378` (clamp/blank, now about 450-452), `api.py:458-473` (`last_tick`, now about 537-551); `cli.py:447-452`/`cli.py:466` not rechecked. ENVIRONMENT.md `api.py:71` is correct (EVERY_ENV is line 71).
2. A one-second interval is allowed (documented). A floor was the card's suggestion; the author left it to Don.
