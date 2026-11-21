# Review PR 1082 @ 11fcaba95e4c59c1bd0097085f7536efd95a6d14 (reviewer teammate-don, 2026-11-21): SHIP

PR: attestation-reporter: pin by test that field_core authn is installed (FP-5). One new test file, no product change. I did not write this head or its lane.

Claims checked on the exact head:
- Product already installs authn: api.py:81 `install_authn(app)` with no open_paths. TRUE.
- New file `8 passed` (my run: 8 passed); whole service dir `450 passed` (my run: 450 passed in 227.74 s). TRUE.
- CI on this head (gh pr checks): compose-smoke, compose-upgrade-smoke, fly-image-smoke, tests 3.11/3.12/3.13/3.14 all pass.

Mutants (each applied to one line, run of the new test file only, file restored by git checkout):
| # | mutant | result | killed |
|---|--------|--------|--------|
| M1 | api.py: remove install_authn | 5 failed, 3 passed | yes |
| M2 | open_paths={/pack.html} | 1 failed, 7 passed | yes |
| M3 | open_paths={/pack} | 2 failed, 6 passed | yes |
| M4 | open_paths={/docs,/openapi.json} | 2 failed, 6 passed | yes |
| M5 | authn.secret_matches always True | 5 failed, 3 passed | yes |
| M6 | authn compares only the first character of the secret | 8 passed | NO (survived) |
| M7 | authn OPEN_PATHS empty (/health protected) | 1 failed, 7 passed | yes |
| M8 | open_paths={/redoc} | 8 passed | NO (survived) |
Total 8 mutants: 6 killed, 2 survived.

Surviving mutants (LOW, not blocking; the PR does not claim them):
- M6: the wrong-secret test uses an independent random 32-hex token, so a prefix/partial comparison is not detected. A wrong secret that shares a long prefix with the real one (or differs only in length) would pin the constant-time full comparison; field_core's own authn tests are the right home for that, I did not check them.
- M8: /redoc is not exercised (only /docs and /openapi.json); the same middleware covers it today.

Not verified: a deployed instance or the Fly entrypoint; other services' middleware; demo mode with FIELD_SHARED_SECRET unset (not claimed); I ran on Windows with the venv, CI covers Linux 3.11-3.14.
Verdict: SHIP. Optional follow-ups: a wrong-secret test with a shared prefix, and /redoc in the parametrised list.
