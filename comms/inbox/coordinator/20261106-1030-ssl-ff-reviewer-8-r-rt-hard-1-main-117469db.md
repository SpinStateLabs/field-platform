# R-RT-HARD-1: adversarial hardening review of field-core operator_auth.py, guarded_operator.py, authn.py
Head attacked: main 117469db324337529025e530c27d8dacbb2af824 (contains the merged G code ede21674). Reviewer ssl-ff-reviewer-8. I attack, I do not fix; no PR head or repo file was changed.
Prior art not repeated: red-team files 20261105-1850, 1851, 20261106-0230, 0340, 1000.

## VERDICT: no ENFORCE authentication or authorisation bypass found in the vectors tested. 2 MEDIUM availability defects in authn.py, 1 MEDIUM audit-integrity question, 3 LOW.

## What I tried (and the result)
Method: ran the merged code under ENFORCE with a real operators file, a FastAPI app using `operator_auth.guard`, raw header bytes via httpx ASGITransport. Scripts (fake keys only, no secrets): hard1.py, hard2.py, hard3.py in my scratchpad D:\temp\claude\D--dev-cache\7b81cf96-44f8-4871-a40c-8f0ef2d472c4\scratchpad\ (run with the repo's src dirs on PYTHONPATH).
- Header handling: valid 200; header-name case variants 200 (normalised, correct); duplicate `x-field-operator` 400; comma-joined id 400; empty id 400; UTF-8 non-ASCII id 400; an alias ("Don Hagell") used as the id 400; id case variant ("Don") 403; revoked row's key 403; key of row A with id B 403 (HIGH, measured).
- Registry faults under ENFORCE: path unset 503; missing file 503; `FIELD_OPERATOR_REGISTRY=0` 503 (fail closed as designed) (HIGH).
- `FIELD_OPERATOR_REQUIRE` with any unknown spelling is ENFORCE (code read, `_require_flag`) (HIGH).
- Verifier rules, through `load_registry`: a row holding kill+revive+revoke+mint with id `svc-verify-x` is REJECTED whole (C-805); a `svc-verifier-` row holding `bypass_operator_list` is REJECTED whole (C-1003) (HIGH).
- Alias-grant contract: `check_granted_by` returns True for an own alias and the delegation mint then calls `check_explicitly_listed` (delegation_authority/api.py:193, 210); revoke paths call `check_list_bound_reach` (api.py:331, 408) (HIGH, code read).
- Contextvar leakage: 300 concurrent requests, async and sync handlers, four credential kinds (valid don, valid ann, wrong key, none; LOG-ONLY so a bad credential is not refused); each handler read `operator_auth.current()`: 0 mismatches (HIGH).
- guarded_operator.py: allowlist is exact (method plus fullmatch path), base-prefix stripped, same-origin checked; `//` and query-string forms fail closed (no pair sent, so the write is refused); `{x}` becomes `[^/]+` with literals unescaped, which only over-matches (harmless: "when in doubt it is listed") (HIGH for the read, no exploit found).

## Findings

### F-H1-1 MEDIUM (confirmed): a non-ASCII `x-field-auth` header makes every service answer 500 instead of 401
`packages/field-core/src/field_core/authn.py:57-58`: `hmac.compare_digest(presented, secret)` is called on `str`s. Python raises `TypeError` when either has a non-ASCII character. Starlette decodes header bytes as latin-1, so an unauthenticated caller sending `x-field-auth` with byte 0xE9 reaches the TypeError inside the middleware.
Repro: FIELD_SHARED_SECRET=s3cret-value; request with raw header bytes `b"s3cr\xe9t"` to any path except `/health` gives 500 "Internal Server Error" (hard1.py). Correct behaviour: 401.
Impact: no bypass (it fails closed), but anyone with network reach can force a 500 and a traceback log per request on every service that uses `authn.install`, and a 500 is not a recorded refusal.
Fix direction: compare `presented.encode("utf-8", "replace")` with `secret.encode("utf-8")`, or compare digests of both.

### F-H1-2 MEDIUM (confirmed): a non-ASCII configured `FIELD_SHARED_SECRET` makes every guarded request 500, including for a correct client
Same line. With the secret "s" + e-acute + "cret": a client sending ASCII `secret` gets 500, and a client sending the exact UTF-8 bytes also gets 500, because latin-1 decoding makes the header non-ASCII (hard3.py). The service is silently unusable except `/health`; nothing validates the secret at startup. Fix: validate the secret at install time (ASCII-only, or encode both sides) and log once.

### F-H1-3 MEDIUM (confirmed; design question for Don): the ledger seals `operator.*` only; other audit-looking event types, and look-alikes of `operator.*`, are accepted from any shared-secret caller
`operator_auth.py:571-612` (`admit_ledger_event`): the refusal test is `event_type.strip().lower().startswith("operator.")`. Measured with the flags armed and no operator headers:
- `"keyrotation.breakglass_used"` is ACCEPTED with the caller's payload (reserved keys stripped, no attribution): forged rotation/break-glass evidence by any perimeter-secret holder.
- `"\u200boperator.breakglass_counters_changed"` (zero-width space prefix), `"\ufeffoperator.x"` (BOM) and `"operator\u2024x"` (one-dot leader) are ACCEPTED, with no `self_reported` stamp and no refusal. `str.strip()` does not remove U+200B or U+FEFF. `"operator.\u200bx"` is refused because it still starts with `operator.`.
- `AppendRequest.event_type` is only `min_length=1` (`services/sealed-ledger/src/sealed_ledger/api.py:59`).
Impact: a forged record that looks like an `operator.*` or break-glass record to a human reading the ledger or the console. It sets no reserved key and does not trigger the G23 alert (that maps the exact name `operator.breakglass_counters_changed` and only from the observer). Whether any perimeter holder may append `keyrotation.*` is Don's design call; today only `operator.` is sealed.
Fix direction: refuse event types outside a charset (for example `^[a-z0-9_.-]+$`) at the ledger, and decide whether `keyrotation.` joins the sealed prefixes.

### F-H1-4 LOW (confirmed): reserved-key stripping is exact-match
`operator_auth.py:243-246, 494-501`: `Operator_Claimed`, `operator_claimed ` (trailing space) and `operator_claimed` plus U+200B all survive `_strip_reserved` and are stored in the payload (hard2.py). Consumers that read the exact key are unaffected; a look-alike key can mislead a human reading the raw event. Nested reserved keys are stripped correctly (list-of-dict case measured).

### F-H1-5 LOW (confirmed): `parse_headers` accepts a trailing newline for dict callers
`operator_auth.py:1368-1371` uses `.match` with `$`-anchored regexes, so `{"x-field-operator": "don\n", "x-field-operator-key": "fok_x\n"}` parses as `('don\n', 'fok_x\n')` (hard1.py). Not reachable over HTTP (a header value cannot carry LF); the id then fails the row compare (403), and `shown_claim` hides it (`(not shown)`, hard3.py). `operator_headers()` already uses `fullmatch`; use it here too.

### F-H1-6 LOW (design note): the machine-verifier scope rule keys on an exact triple
`operator_auth.py:684-694`: only a row holding all of kill, revive, revoke plus mint or mint_for_others, and no `*`, is rejected when its id lacks the `svc-verifier-` prefix. A row with `kill, revive, mint, mint_for_others` (no `revoke`) and an ordinary id LOADS (hard3.py) and, being unbound, passes an empty or absent `authorized_operators` list (`check_authorized`: empty list means authentication only). That is current policy for ordinary rows, so this is a note only: verifier-like power minus `revoke` is not caught.

## Not checked (stated, I do not know the result)
Format 2 key-window boundary arithmetic and `next_key` rollover under a mutated clock; passkey/session `auth` paths; `_apply_retired_memory` and registry snapshot caching under concurrent file replacement; file-read limits (symlink, oversize, BOM beyond the existing tests); `operator_health.guard` and `op_health.note_refused`; websocket routes (none searched; `authn` is an http middleware); behaviour on the GX10; timing of `_verify`.

## Suggested builder cards (the coordinator adds them; I do not edit WORKLIST.tsv)
1. authn: ASCII-safe constant-time compare and secret validation at install (F-H1-1, F-H1-2; field-core authn.py, tests with a raw non-ASCII header and a non-ASCII secret).
2. sealed-ledger: event_type charset, and a ruling on sealing `keyrotation.` (F-H1-3).
3. `parse_headers` to `fullmatch` (F-H1-5); reserved-key case/whitespace normalisation (F-H1-4).
