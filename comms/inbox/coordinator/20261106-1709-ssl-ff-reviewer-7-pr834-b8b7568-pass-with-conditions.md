# Review PR 834 (G27: d16_record_check, read-only check that the D16 positive write is recorded) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `b8b7568ce7d801fee2471b8219d287cf26c46fa9`.
Condition C1 (runbook wording, no code change): the runbook paragraph and the tool's docstring must state that the check proves the write only when the operator layer was NOT OFF when the row was written. Under OFF, a perimeter-secret holder can write a row that passes this check (reproduced below). Condition C2: CI on the head. The code does what the PR says, reads only, and leaks nothing I could provoke.

## Objections first
1. Forgeable under OFF (HIGH, reproduced). The check trusts three payload fields (`operator_id_authenticated`, `operator_claimed`, `operator_key_fp`). `admit_ledger_event` returns the payload untouched when the mode is OFF (operator_auth.py:588-589). I started the real sealed-ledger app in OFF, POSTed `{"operator_id_authenticated":"don","operator_claimed":"don","operator_key_fp":"abcd1234"}` as an ordinary `x.forged` event (201, stored as written), and `check_events` returned PASS ("1 signed authenticated row(s)"). In LOG-ONLY (registry file present, mode log-only) the same POST stored an EMPTY payload (the reserved keys were stripped; "operator attribution LOST" was logged) and the check FAILED correctly. So the check is sound when the layer is armed (LOG-ONLY or ENFORCE) and the writer is not a service holding `ledger_attribute` for that event type, and meaningless under OFF. The tool does not read the mode.
2. The tool does not verify the chain or the row's origin: it does not call `/ledger/verify` and does not require an event type that a guarded write produces (any event type passes). A `ledger_attribute` service (by design the legitimate writer) can write the fields for the event prefixes its identity covers.
3. "signed" in the output ("N signed authenticated row(s)") reads like a cryptographic signature; the fields are server-side attribution, not a per-event signature (F2 signing is separate). LOW wording.
4. Window: `GET /ledger/events` has no limit by default (`limit` None, up to 10,000 when given); estate_probe caps a response at 16 MiB and returns `response_too_large`, which this tool reports as "could not be read" (exit 2). On a very large ledger the check cannot run over `--base`; use `--events` with a filtered file. By reading; not reproduced at that size.

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Sonnet 5.5; .github/: 0 files. 3 files: tools/d16_record_check.py (+127), tools/tests/test_d16_record_check.py (+91), runbook paragraph (+6, addition only). Based on 117469db; main is e125a878; no overlap in these files.
- Field names verified against the code: `operator_id_authenticated`, `operator_claimed`, `operator_key_fp` are the keys `OperatorAuth` writes (operator_auth.py:417-419); the ledger `GET /events` answers a JSON list of events with `payload` and `hash` (measured on the real app), which is what the tool reads.
- Leak probes: it prints ids, the event type and the first 12 characters of the event hash only; `--operator-id fok_abc` is refused (exit 2, "must be an operator id, not a key"); a hostile event type is shown as "(not shown)"; the secret file is read and sent as a header only.
- Behaviour: an empty ledger fails (exit 1); unreadable events or a usage error exit 2; found exits 0.
- Tests: test_d16_record_check.py 15 passed; the lints the PR cites plus doc anchors: boundary-echo, deploy-docs, environment-doc and http-env-proxy files 260 passed; `environment_anchors --check` 0 wrong rows.

## Mutants (20; counted from the table)
| group | mutants | killed | survived |
|---|---|---|---|
| matching and proof rules A1-A8 (id not compared, claimed-only counts, claim or fingerprint not required, empty claim, fp regex any / 7 hex, ok on any row) | 8 | 7 | 1 (A7) |
| output hygiene A9-A13 (full hash, 40-char hash, event type unchecked, authenticated id unchecked, fok_ allowed in the display mask) | 5 | 3 | 2 (A12, A13) |
| A14 empty ledger passes | 1 | 1 | 0 |
| usage and exit codes U1-U6 (both inputs, no secret file, exit 1 on unreadable, exit 0 on not found, key as id, dict not unwrapped) | 6 | 4 | 2 (U1, U5) |
Totals: 20 mutants, 15 killed, 5 survived (8+5+1+6 = 20; 7+3+1+4 = 15; 1+2+0+2 = 5).
Survivors: A7 (a 7-hex fingerprint is accepted: the 8-hex boundary is unpinned); A12/A13/U5 (the id display guard, the `fok_` mask and the CLI `fok_` refusal each cover for the other, so removing one leaves the key hidden; none is tested alone: with BOTH removed a key given as `--operator-id` would print); U1 (passing both `--events` and `--base` is not refused; harmless). All LOW.

## Optional LOWs (new PR)
Pin the 8-hex length, the fok_ refusal, and both-inputs usage error; have the tool print the operator mode caveat (or read `GET /ledger/verify`); rename "signed authenticated" to "authenticated".

## Not verified
CI/GX10; Linux; a real armed estate (my forgery test used the in-process app in OFF and LOG-ONLY, not a service holding `ledger_attribute`); a 16 MiB ledger.
