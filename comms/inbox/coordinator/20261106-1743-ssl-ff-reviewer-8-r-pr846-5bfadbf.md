# Review R-PR846-5bfadbf: PR 846 (sealed-ledger: refuse look-alike event types; normalise the sealed operator. prefix test; B-RT1, F-H1-3)
Head reviewed: 5bfadbfd17f0576c647733a4d27f4e520da8962d. Head is a fast-forward of main 117469db (HIGH). I reported the finding it fixes (F-H1-3 in R-RT-HARD-1); I am not the author.

## VERDICT: PASS

## Checks (HIGH, run by me)
1. Identity: 1 commit 5bfadbfd, author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 5 files (operator_auth.py, sealed-ledger api.py, a new test file, one edited test, one runbook note).
2. Code read: `AppendRequest.event_type` is `Field(min_length=1, pattern=r"^[a-z0-9_.-]+$")`; the sealed-prefix test is now `_sealed_prefix_form(event_type).startswith("operator.")` where the form is NFKC, then a translate table dropping U+00AD, U+034F, U+061C, U+180E, U+200B-U+200F, U+2060-U+2064, U+FEFF and U+202A-U+202E, then strip and lower; used in `admit_ledger_event`, `may_attribute` and `reject_reserved_event_type`. Acceptance of an `operator.*` type still needs the exact type in `SELF_REPORTABLE_EVENT_TYPES`.
3. Tests on head: test_event_type_charset_rt1 17 passed; test_operator_health_g_sealed_ledger 23 passed.
4. Probe of `AppendRequest` (et_probe.py in my scratchpad): refused: `a.b` plus LF, CR LF, leading LF, upper case, space, U+2028, zero-width-space prefix, U+2024 dot leader, Cyrillic a, fullwidth a, slash, colon; accepted: `agent.registered`, `operator.refused`, `keyrotation.breakglass_used`. The pydantic pattern does not accept a trailing newline (the `$` pitfall I flagged for `parse_headers` does not apply here).
5. Regression risk scan (AST over services, packages and tools, non-test code): 11 literal ledger event types found, all inside the charset; 41 dynamic sites (variables and one f-string `federation.{allow|block|escalate}`) are not statically checkable. The author's claim that every `event_type=` literal passes holds for my scan too; positional literals (the common form, for example `ledger.append("operator.unauthenticated", ...)`) also pass. A dynamic type outside the charset would now be a 422 at the ledger; I did not run every service end to end.
6. Mutants, 12 run: 10 killed, 2 survived (counted from table).
| # | Mutant | Result |
|---|---|---|
| P1 | pattern removed | killed |
| P2 | upper case allowed | killed |
| P3 | colon allowed in the charset | SURVIVED (LOW: the charset boundary is tested for upper case and look-alikes, not for punctuation such as `:`) |
| P4 | `+` becomes `*` | SURVIVED (equivalent: `min_length=1` already refuses an empty string) |
| P5 | end anchor dropped | killed |
| P6 | start anchor dropped | killed |
| S1 | no NFKC | killed |
| S2 | invisible characters not removed | killed |
| S3 | no lower-casing | killed |
| S4 | `admit_ledger_event` back to the old test | killed |
| S5 | `may_attribute` back to the old test | killed |
| S6 | `reject_reserved_event_type` back to the old test | SURVIVED (LOW: that function is marked DEPRECATED and only tests call it; behind the charset it cannot be reached over HTTP) |
7. Docs: the one-line note in `docs/runbooks/ntfy-alerts.md` says `keyrotation.` is not sealed here and `keyrotation.breakglass_used` is accepted today, pinned by a test: consistent with what I measured. That half of F-H1-3 stays Don's ruling (PR 57 rework, C-496); this PR does not claim to close it.

## Observations (LOW, not conditions)
- No maximum length on `event_type` (a 5000-character type is accepted, as before); a cap such as 128 would bound it.
- Degenerate types `.`, `-`, `0` are accepted by the charset.
- With the charset in place, `_sealed_prefix_form` is defence in depth for HTTP callers and still matters for direct callers of `admit_ledger_event`.

## Not verified
Dynamic event-type sites at run time; full sealed-ledger and field-core suites; GX10 16/16.

## Head frozen at 5bfadbfd. Optional LOWs (punctuation test, length cap) in a NEW PR.
