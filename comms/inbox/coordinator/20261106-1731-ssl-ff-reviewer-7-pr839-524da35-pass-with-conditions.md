# Review PR 839 (authn: compare x-field-auth as bytes; non-ASCII header or secret is 401, not 500; RT1 F-H1-1, F-H1-2) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `524da3594d5d1d85a732ad92efa7bdd93eb3dedb`.
Conditions: C1 (landing order, HIGH): this PR and PR 828 (per-tier keys, my PASS WITH CONDITIONS on d9a78c02) both rewrite the same comparison in `authn.py`; a trial merge conflicts (`git merge-tree` reports a content conflict in packages/field-core/src/field_core/authn.py). Whichever lands second must keep THIS PR's byte rule: 828's `_same` encodes the presented header as UTF-8, which for a non-ASCII secret never matches (the server hands over the raw header bytes decoded as latin-1; this PR re-encodes them as latin-1 to recover the raw bytes, then compares with the UTF-8 secret). 828's `_same` (used for the full key and the read key) should call `secret_matches`. C2: CI and GX10 on the head. The fix itself is correct.

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Sonnet 5.5; .github/: 0 files. 2 files: authn.py (+20/-1), tests/test_authn.py (+88). Base == main e125a878.
- Defect reproduced and fixed, by my own probe through a raw ASGI scope on the head (secret "s3cret"): header `s3cret` -> 200; `s3cret\xe9` -> 401; `\xff\xfe` -> 401; `s3cret\xc3\xa9` -> 401 (no 500s). On main the same non-ASCII headers raised `TypeError` in `hmac.compare_digest` (str, non-ASCII), as the PR and the red team report.
- Code read: `secret_matches` encodes the presented str as latin-1 (a character beyond latin-1 cannot occur from a server header; it returns False rather than raising), encodes the secret as UTF-8 with surrogatepass, and compares bytes with `hmac.compare_digest`; `install()` logs one warning naming only the variable and the header when the configured secret is non-ASCII (the value never logged); `/health` stays open; ASCII behaviour unchanged.
- Tests on the exact head (Windows): test_authn.py 13 passed (7 new, raw-ASGI driven); whole field-core suite 1648 passed, 2 skipped.
- Other `compare_digest` sites checked: operator_auth and operator_health compare hashes of the presented key (fine); `services/force-gateway/src/force_gateway/api.py:260` compares `presented_auth.encode("utf-8")` with the secret in UTF-8: no crash, but for a non-ASCII secret it never matches the latin-1-decoded header (LOW, passthrough exemption path only; not changed by this PR).

## Mutants (14 on authn.py vs test_authn.py; counted from the table)
| # | mutant | result |
|---|---|---|
| A1 | old str `compare_digest` restored | KILLED |
| A2 | presented encoded as UTF-8 (the 828-style rule) | KILLED |
| A3 | presented encoded ASCII, ignoring errors | KILLED |
| A4 | non-latin-1 header encoded with `replace` | SURVIVED |
| A5 | secret encoded latin-1 | KILLED |
| A6 | `==` instead of `compare_digest` | SURVIVED |
| A7 | always False | KILLED |
| A8 | always True | KILLED |
| A9 | a header that is a PREFIX of the secret accepted | SURVIVED |
| W1 | no warning for a non-ASCII secret | KILLED |
| W2 | warning for every secret | KILLED |
| W3 | warning contains the secret | KILLED |
| W4 | warning contains a fragment of the secret | KILLED |
| O1 | /health no longer open | KILLED |
Totals: 14 mutants, 11 killed, 3 survived (11+3 = 14). A4: the branch cannot be reached from a real server (headers decode as latin-1, so every character fits); equivalent. A6: a timing property no functional test can see (read by inspection only). A9: real, LOW-MEDIUM: no test sends a header that is a strict prefix of the secret, so a regression to prefix matching would pass the suite; add one case (secret "s3cret", header "s3").

## Optional LOWs (new PR)
Prefix and longer-than-secret header cases; align force-gateway's passthrough comparison with `secret_matches`.

## Not verified
CI/GX10; Linux; a real client library sending a non-ASCII secret (the PR says one that ASCII-encodes header values cannot; not reproduced); the service suites that install authn (not run by me for this PR).
