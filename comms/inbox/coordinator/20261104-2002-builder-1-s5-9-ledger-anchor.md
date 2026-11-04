S5-9 sealed-ledger anchor CLI. PR #685 (draft). 12 tests, 6 mutants killed, lint tests pass, allowlist line added.
Proved: garbage PEM and RSA both raise ValueError from sign_manifest.
Open: NUL byte in --anchors still tracebacks (click stats Path options during parsing). test_operator_observer_c6_serve errors on main too (env).
