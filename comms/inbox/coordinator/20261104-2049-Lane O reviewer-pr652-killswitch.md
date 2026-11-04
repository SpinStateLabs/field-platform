# LANE O review: PR 652 (kill-switch S4-4 hardening) @ 95a7b137

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head 95a7b137: code+test commit 9da93cd6 and a docs anchor refresh 95a7b137; 0 behind origin/main, 2 ahead; both commits Don Hagell numeric noreply. api.py +21/-4, tests +163, docs/ENVIRONMENT.md 1 line.

Objections first: (1) `test_a_normal_kill_still_works_and_keeps_the_text_as_sent` only asserts HTTP 200; its name claims the text is kept as sent, and the code comment says "The value is kept as sent". Nothing pins that, so a validator that returns `value.strip()` passes (measured). (2) Control-character refusal is category `Cc` only; zero-width and bidi characters (category `Cf`) pass in the heartbeat id and in operator/reason. The PR does not claim to cover them, but the id is a row key. (3) Allowlist lower-casing is plain `.lower()`, not casefold or IDNA; non-ASCII hosts are not claimed.

Baseline (unmutated, measured): new file 72 passed; kill-switch suite 342 passed. `python tools/environment_anchors.py --check` at this head: 0 wrong anchor row(s); the docs line moved 294 -> 307 and `api.py:307` is the real `os.environ.get("FIELD_KILL_ENDPOINT_ALLOWLIST"...)` line.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 blank operator/reason refused | 5 | 5 | 0 | 0 |
| B2 length bounds 200 / 1000 | 6 | 6 | 0 | 0 |
| B3 allowlist lower-cased, match exact | 6 | 6 | 0 | 0 |
| B4 heartbeat POST bounds the id (len 128, control char) | 7 | 7 | 0 | 0 |
| B5 the 422 does not echo the id, status stays 422 | 4 | 4 | 0 | 0 |
| B6 kept as sent (validator returns the value unchanged) | 1 | 0 | 0 | 1 |
| Total | 29 | 28 | 0 | 1 |

Totals counted from the table: 29 = 28+0+1; no invalid, no noapply. B6 was added after the first 28 and run on its own (file 72 passed, whole kill-switch suite 342 passed).

Survivor (real gap): B6 `return value.strip()` in `KillRequest._not_blank`. Add an assertion that the ledger row or response carries the operator and reason unchanged (e.g. a value with inner and outer padding).

Condition: add that assertion; consider whether `Cf` characters in the heartbeat id are in scope. Confidence: HIGH on counts, MEDIUM on gap classification. Token/cost: I do not know.
