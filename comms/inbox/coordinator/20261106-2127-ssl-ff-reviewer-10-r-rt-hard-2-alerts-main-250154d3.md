# R-RT-HARD-2: adversarial hardening review of merged G23 (field-core alerts.py and alert_senders.py)
Head attacked: main `250154d3f` (the card names `ede21674`; `alerts.py` and `alert_senders.py` are unchanged between them as far as I can tell: I read them on `250154d3f`, and the red-team re-run of 20261106-0340 says G23 touches only alert, controller and ledger-health files). Reviewer ssl-ff-reviewer-10. I attack, I do not fix; no repo file or PR head was changed. Fake topic and token only; no secret appears here.
Prior art not repeated: red-team files 20261105-1850, 1851, 20261106-0230, 0340, 1000 (they cover the stage controller and note "sender never raises (HIGH), content check runs" without testing it).
Repro scripts: D:\dev-cache\r10\rt2\a1.py (content check), a2.py (proxy, redirect, leaks, never-raise), a3.py (observer simulation); stdlib plus the repo's field_core and sealed_ledger on PYTHONPATH. Environment: Windows 10, Python 3.14. Everything below was run, except where marked "code read".

## VERDICT: no way found to make an alert carry the topic, the token or a contiguous key, hash or token; no raise into a caller; the proxy environment and redirects are ignored. 1 MEDIUM design gap (a separated hash or fingerprint passes the content check), 1 MEDIUM operational (break-glass alerts are synchronous inside the observer tick and uncoalesced), 4 LOW.

## Findings

### F1 MEDIUM, confirmed (HIGH confidence, measured): a hash or fingerprint with separators passes `content_problem`
`alerts.py` `_HEX_RUN_RE = [0-9A-Fa-f]{12,}`; the field charsets allow `. : - _ @` in `estate` and `subject` and any printable ASCII (space included) in `detail`. a1.py: a 64-hex sha256 written `ab:cd:ef:...` (2-character groups, the openssl and ssh display form) passes (None); a 16-hex fingerprint written `ab12-cd34-ef56-ab78`, `ab12_cd34_ef56_ab78`, `ab12.cd34.ef56.ab78` or `ab12cd34 ef56ab78` passes; and `render` delivers it: body contains `ab12-cd34-ef56-ab78`, withheld fields `()`. A contiguous 12+ hex run, a 32+ opaque run, `fok_` and `tk_` (any case) and a PEM header are all caught; an 11-hex run passes (a 44-bit prefix).
The module docstring promises "no run of 12+ hex digits (a hash or a 16-hex fingerprint)". That holds for contiguous values only, which is what an accidental inclusion looks like; the repo's own fingerprints (`key_fingerprint`, 16 hex) are contiguous, so I found no emitter that produces the separated form. It is a gap against the stated rule, not an exploit.
Fix direction: strip `[\s:._-]` before the hex test (and the opaque test), or refuse any field with 12 or more hex digits in total.

### F2 MEDIUM, confirmed by simulation (operational): the break-glass alert is sent synchronously inside the observer tick, and is not coalesced or rate-limited
`operator_observer._observe_rotation` calls `_raise_alert` (-> `alert_senders.alert_for_event` -> `alerts.send`) inline, inside `observe_once`, which holds `self._lock` and walks every target in turn. `send` blocks for up to `max_attempts * timeout_s + back-off` = 3 x 5 s + 1 s + 2 s = 18 s per alert when ntfy is slow or failing (429 and 5xx are retried). a3.py with the real `OperatorObserver` and a 0.5 s alert: nine sources each seeing the break-glass attempt counter go up once per tick gave 9 rows and 9 alerts per tick and a 4.5 s tick; with the real 18 s worst case that is about 2.7 minutes per tick, so the audit rows and the registry/mode observations of every target after the first alert in a tick are delayed by that long (written late, not lost).
Who can cause it: any caller holding the perimeter secret can send a guarded write claiming `x-field-operator: don-breakglass` with any key; `authenticate`'s `fail()` calls `note_breakglass(used=False)` (code read, operator_auth.py), which bumps `breakglass_attempt_count` on that service; the observer turns each changed counter into one row and one priority-5 (urgent) alert per source per tick. The compose default tick is 60 s (docker-compose.yml l.222, `FIELD_LEDGER_OBSERVE_EVERY:-60`; minimum 5 s), so the bound is one urgent alert per service per 60 s, roughly nine a minute across the estate, for as long as the attempts continue. Whether an attempt storm should wake Don once or on every tick is a design call; there is no cap or aggregation in `alerts.py`.
Fix direction: send the alert from a worker thread (or `asend`) so the tick never waits on ntfy, and coalesce `breakglass_used` per service for a window.

### F3 LOW (confirmed): `alert_senders.py` docstring is stale about the stage controller
It says `stage_transition` and `stage_aborted` "wait for the Phase G stage controller, which is not in this repository". The controller is on main (`tools/stage_controller.py` imports `alert_senders` and calls both senders per step and on abort; the rollback runs before the aborted alert, so a slow ntfy cannot delay a rollback). The runbook table (ntfy-alerts.md l.95-96) is correct for the three rotation classes.

### F4 LOW (confirmed): the per-step `stage_transition` alert is synchronous in the controller
`stage_controller.py` l.331 sends after every step; with ntfy unreachable each step costs up to the same 18 s, so a three-step stage runs about a minute longer with the estate half-armed. Not unsafe (the abort path rolls back first, then alerts), but the half-armed window is longer exactly when alerting is broken.

### F5 LOW (confirmed): field regexes use `match` with `$`, which accepts a trailing newline
`estate` and `subject` (`^[A-Za-z0-9._@:-]{1,64}$`) and `detail` (`^[ -~]{1,200}$`) accept one trailing `\n`: `estate="gb10\n"` renders `estate: gb10` followed by an empty line, withheld `()` (a1.py). An inner newline is refused (detail) as designed. Cosmetic (the body has no injection beyond one blank line) but it contradicts the "narrow charset" statement; use `fullmatch`.

### F6 LOW (confirmed): `Destination` redacts `repr`/`str` but `dataclasses.asdict` returns the URL and topic
a2.py: `repr(dest)` and `str(dest)` are `Destination(configured, token=yes)`; `json.dumps(dataclasses.asdict(dest))` contains the topic. No code in the repo does that (grep), so nothing leaks today.

## Checked, no finding
- Topic, token and URL never printed: health fields, all log output (root logger at DEBUG during failed, redirected and 500 sends), `repr(AlertResult)` and `repr(Destination)` contain no fragment of the topic (first 12 characters) or token (a2.py section 5).
- Proxy environment: `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` set to a live local listener; the alert went straight to the target (target saw 1 request with the topic path and the bearer token, proxy saw 0). Redirects: a 302 to a second listener was not followed (reason `http_302`, the second listener saw 0).
- Failure counting and reasons: 500 retried three times then `http_500`; unreachable gives a fixed reason (`timeout` here: Windows takes longer than the 1 s deadline to refuse a loopback connect); `not_configured` and `topic_invalid` fixed tokens.
- Never raise: `alert_senders.*` returned a result (reason `sender_error_<Type>`) for a subject or detail whose `__str__` raises, a bad `max_attempts`, a bad `timeout_s` and a non-mapping `env`; `alert_for_event` returned a result for payloads of `None`, an int, a string, a list, a dict holding objects and a 5,000-digit string. Only `alerts.send` itself raises ValueError for an unknown class (documented programming error; the senders cannot reach it).
- The configured topic is caught by the exact-substring check case-insensitively; a 32-plus-character topic is also caught by the opaque-run rule. A partial topic (first 15 characters), the topic with `-` removed, or reversed are not caught (the full-length topic of `new_topic()` is 38 characters, so any 32 contiguous characters of it are caught).
- Non-ASCII fields are refused by the charset (fail closed): confusable letters cannot pass.
- One alert per written break-glass row (observer docstring and a3.py: nine changed sources gave nine rows and nine alerts, no duplicates); a failed row write is retried next tick and does not alert twice.
- Existing tests: field-core alert tests 143 passed, 1 skipped on main.

## Not checked (stated)
Live ntfy behaviour (rate limits, the real response to a 429 or an oversize body: not in source, general knowledge only); Linux socket behaviour; the rotator call sites (not on main); the 1,024-byte body truncation boundary beyond reading (`data = body.encode()[:1024]` can cut a multi-byte character, and the field charsets are ASCII so it cannot occur today); `field alert-test`'s default estate (host name; hex container ids are withheld, as the module says); any estate.

## Suggested builder cards (the coordinator adds them; I do not edit WORKLIST.tsv)
1. F1: normalise separators before `content_problem`'s hex and opaque tests; tests for `ab:cd:...`, `ab12-cd34-...` and space-grouped forms.
2. F2: send the observer's alert off-thread and coalesce `breakglass_used` per service per window; a test that a slow alert does not delay the next target's rows.
3. F3 and F5: fix the docstring; `fullmatch` for the three field regexes.
