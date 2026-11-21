# Linux reproduction of the "9 Windows failures" (4 tools/tests modules)

Base: cb7a94f8 (main). Host: Linux 6.18, Python 3.13.18, bash at /usr/bin/bash.
Deps: venv, installed as `.github/workflows/ci.yml` does (`-c integration/constraints.txt -c integration/ci-constraints.txt --build-constraint integration/build-constraints.txt`, field-core[dev] + all services `--no-deps`, then fastapi uvicorn httpx pytest). `anthropic` is not installed (claude-approver is `--no-deps`, as in CI); none of the four modules needs it.

## Where the "9 Windows failures" were recorded
Not found in the tracked repo. Searched `STATE.md` (grep -a), `tasks/*.md`, `CHANGELOG.md`, `docs/`, and `git log --grep`. The only Windows-related hits are unrelated (STATE.md:215-224 gate check; STATE.md:1181 MSYS path trap; tasks/todo.md:1149 WinError 32; docs/runbooks/token-renewal.md Windows runs of test_renew_token). STATE.md:222 points to `../tasks/windows-gate-verification-2026-09-12.md`, which lives outside this repo and was not available. The figure of 9 and the failing test names are therefore NOT VERIFIED from repo sources.

## Linux results (CI=1)
Combined run: `CI=1 python -m pytest -q -rfEs tools/tests/test_ci_external_ref_guard_c101.py tools/tests/test_compose_resolved_bind_c512.py tools/tests/test_fly_identity_c5.py tools/tests/test_ssl_renewal.py`
Last line: `243 passed, 2 skipped in 114.25s (0:01:54)`

| Module | Result |
|---|---|
| test_ci_external_ref_guard_c101 | 31 passed |
| test_compose_resolved_bind_c512 | 89 passed |
| test_fly_identity_c5 | 123 passed, 1 skipped |
| test_ssl_renewal | 1 skipped |

Skips (not failures):
- test_ssl_renewal.py:50 "Windows-only: the ssl agents' client is Windows PowerShell" (cannot be reproduced on Linux).
- test_fly_identity_c5.py:216 base commit 14fed1ee not in this shallow clone; the sha256 pin stands.

## Conclusion
0 failures reproduce on Linux; no product defect found; no code changed. Any Windows-side failures remain unreproduced here and are plausibly environment-only (CRLF in `.sh`/templates, path separators, bash availability; STATE.md:2064 records a CRLF/.sh incident), but that is an untested hypothesis (LOW confidence). Triage needs the actual Windows failure output (names plus first error lines).
