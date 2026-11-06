# Review PR 843 (operator_auth: parse_headers fullmatch; normalised reserved-key strip; RT1 F-H1-4, F-H1-5) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `177e4ce8e09b425164eaf57a8dd35ec8e71e5c4a` (no conditions beyond the standard CI and GX10 on the landed head).

## Checks (HIGH, run by me)
- Identity: 2 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files. 3 files: operator_auth.py (+18/-4), the new test file (+96), docs/ENVIRONMENT.md (+2/-2: the two FIELD_OPERATOR_REGISTRY/REQUIRE first-read cells re-anchored, +1 line). Base e125a878; main has since moved (ccab2379) and a trial `git merge-tree` is clean.
- Code read: `parse_headers` uses `fullmatch` for the operator id and the key, so a trailing or leading newline (which `$` used to allow) is now `400 malformed operator credential headers` with the fixed text, no echo of the key. `_is_reserved(key)`: non-string keys are not reserved; an exact name is; otherwise NFKC, drop Unicode format characters (category Cf), strip, casefold, then test membership in the five reserved names; used by both `_has_reserved` and `_strip_reserved`, so reserved look-alikes are removed at every depth. Only the TEST is normalised: a key that is not a reserved look-alike is stored exactly as sent. Flags OFF: `merge_payload` is unchanged.
- Own probe of `_is_reserved` over 25 spellings of `operator_claimed` and relatives: reserved (stripped): plain, UPPER, trailing space, trailing newline, leading tab, NBSP, ideographic space, zero-width space, BOM, soft hyphen, word joiner, left-to-right mark, a tag character, fullwidth, fullwidth plus zero-width space. Not reserved (stored as sent): a combining grapheme joiner (U+034F), a variation selector (U+FE0F), a combining acute, a NUL suffix, and cross-script look-alikes (Cyrillic о, small-cap ᴏ, dotless ı, the Angstrom sign letter variant). The PR names cross-script homoglyphs as out of scope. The others (Mn marks, NUL) are not folded either; harmless today because every reader of these fields (the ledger consumers and tools/d16_record_check.py) matches the exact name, so a decorated key is simply an unread extra key. Defence in depth only (LOW).
- Tests on the exact head (Windows): the new file 78 passed; whole field-core suite 1717 passed, 2 skipped; `environment_anchors --check` 0 wrong rows.

## Mutants (17 on operator_auth.py vs the new file and test_operator_auth.py; counted from the table)
| # | mutant | result |
|---|---|---|
| N1 | NFKC dropped | KILLED |
| N2 | format characters kept | KILLED |
| N3 | strip dropped | KILLED |
| N4 | casefold dropped | KILLED |
| N5 | `lower()` instead of `casefold()` | SURVIVED (equivalent: none of the five reserved names contains a letter whose casefold differs from its lowercase) |
| N6 | exact-name fast path removed | SURVIVED (equivalent: normalising an exact name returns it) |
| N7 | non-string key counted as reserved | KILLED |
| N8 | substring match (over-strip) | KILLED |
| N9 | prefix match (over-strip) | KILLED |
| H1 | `_has_reserved` exact match again | KILLED |
| H2 | `_strip_reserved` exact match again | KILLED |
| H3 | strip not recursive into lists | KILLED |
| H4 | `_has_reserved` ignores nested values | KILLED |
| P1 | operator id `.match` again | KILLED |
| P2 | key `.match` again | KILLED |
| P3 | malformed status 403 | KILLED |
| P4 | malformed text echoes the key | KILLED |
Totals: 17 mutants, 15 killed, 2 survived (15+2 = 17), both survivors equivalent.

## Optional LOWs (new PR)
Fold Mn marks and Cc controls out of the test as well (or document that readers must match exact names, which today they do); a cross-script look-alike corpus as a named limit in the docstring (the PR already states it).

## Not verified
CI/GX10; the service suites that use the ledger attribution path (the PR reports sealed-ledger operator/attribution tests 131 passed with one environment error, not re-run by me); Linux.
