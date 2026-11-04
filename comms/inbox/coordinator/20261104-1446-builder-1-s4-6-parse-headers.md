# builder-1 S4-6 (field-core operator_auth.parse_headers)
PR: https://github.com/SpinStateLabs/field-platform/pull/654 (draft), head 448c8c82.
Ran: tests/test_operator_parse_headers.py 32 (2 red before: trailing newline); 5 mutants caught (2, 2, 1, 1, 3 failed); 1 equivalent mutant survives (the explicit empty check is redundant with the regex {1,N}); packages/field-core/tests 1576 passed, 2 skipped (incl. test_operator_auth, _stage0, _format2).
Fix: _OPERATOR_RE and _KEY_RE applied with .fullmatch in parse_headers (2 lines); 400 text unchanged. Severity low (HTTP servers normally strip a trailing newline); reachable via the in-process dict path.
Not changed: _HEX64 (^...$) and the key-file check (stripped first).
