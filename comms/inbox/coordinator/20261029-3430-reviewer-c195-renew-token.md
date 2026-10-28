# C-195 reviewer report: tools/renew_token.py on fix/renew-token-signed @8269445 (C-31 re-review, head unchanged)

VERDICT: PASS with LOW findings (test gaps only; no defect proven). Not a merge decision.

OBJECTIONS FIRST
1. A mutation score of 128 of 157 killed says what the tests pin, not what is correct; 19+10 survivors may be equivalent or real gaps and I did not separate them one by one.
2. The tool touches the signed token store and (on mint/revoke) sends operator credentials; one unpinned refusal on that path matters more than the average mutant.
3. Samples a/b were random draws, not the whole file; line ranges 1-600 and 1000+ of generator v1 were not run in this window.

ASSUMPTIONS
1. Head 8269445; module facts from my earlier reading: output redacts secret and operator key; refuses cleartext non-private base when a secret or key is present (validate, ~L1496); operator pair sent on mint and revoke only; exit codes 0/1/2/3; journal and atomic store swap. [MEDIUM: from notes]
2. 171 tests pass in 70 s (runpt19.py). [HIGH]

REASONING
1. Generator v1, lines 600-1000: 131 run, 112 killed, 19 survived (log ~/ff-work/c195d.log). Generator v2 sample a: 12 run, 5 killed, 7 survived; sample b: 14 run, 11 killed, 3 survived. Totals 157 run, 128 killed (81.5%), 29 survived (some overlap by line, e.g. L462). [HIGH on the counts]
2. Survivors that matter: L700-712 (token-record validation: each `if not ...: raise` with the branch removed: token_id UUID, agent_id, granted_by, scope, issued_at/expires_at, revoked bool). 7 independent survivors, so a store row with a malformed field is not pinned to be refused at load. L961/L963/L965/L979 (revoked, expired and renew-within boundary comparisons: `<=` to `<` survives, so the exact-boundary day is unpinned). L622 (errno held-set branch). [HIGH it survives; whether downstream code would still refuse is not shown]
3. Survivors that are labels or hints: L807 grantor wording, L944 401 hint text, L976 clamp note, L777/L800/L852/L895 `isinstance(tok, int)` early-outs, L300 env key name, L405 operator header name `x-field-operator`, L462 store-not-readable message, L763/L856/L966/L1124 labels, L209 prefix label. The L405 header name matters in one respect: renaming it would make mint and revoke send no operator identity and no test fails. [HIGH]
4. L321 `repr(secret)[1:-1]` constant 1 to 2 survives: the redaction of the escaped form of a secret leaves its first character visible; no test pins escaped-form redaction. Leak is one character of a secret that contains characters repr escapes; low impact. [HIGH it survives; impact MEDIUM]

CONCLUSION
PASS (LOW rows below). Pin: (a) one test per L700-712 field with a bad value, expecting the exit-2 refusal; (b) boundary tests at exactly 0 and exactly renew_within_days left; (c) a test that mint and revoke send `x-field-operator`; (d) escaped-form redaction with a secret containing a quote or backslash. Not done: v1 ranges 1-600 and 1000+, per-survivor equivalence analysis.
