# Linux reproduction of the "9 Windows failures" (4 tools/tests modules)

Base: cb7a94f8 (main). Host: Linux 6.18, Python 3.13.18, bash at /usr/bin/bash.
Deps: venv, installed as `.github/workflows/ci.yml` does (`-c integration/constraints.txt -c integration/ci-constraints.txt --build-constraint integration/build-constraints.txt`, field-core[dev] + all services `--no-deps`, then fastapi uvicorn httpx pytest). `anthropic` is not installed (claude-approver is `--no-deps`, as in CI); none of the four modules needs it.

## Where the "9 Windows failures" were recorded
Source: the body of PR #1080 (merged 2026-11-21, "fly.toml: [[vm]] cpus = 4 ... (T9)"). It records a full `tools/tests` run of `9 failed, 4671 passed, 29 skipped in 7892.80s`, with the 9 failures as test_ci_external_ref_guard_c101 x4, test_compose_resolved_bind_c512 x2, test_fly_identity_c5 x1 and test_ssl_renewal x2. It says they fail identically on origin/main cb7a94f8 (`9 failed, 248 passed, 9 skipped` on those four files) and attributes them to the Windows/bash environment. #1080 gives module counts only, not test names or error text.

Tension with this report: on Windows test_ssl_renewal ran and failed 2 tests (per #1080), while on Linux the whole module is skipped at import (`test_ssl_renewal.py:50`), so the ssl part cannot be reproduced or checked here.

Not recorded in the tracked repo files. Searched `STATE.md` (grep -a), `tasks/*.md`, `CHANGELOG.md`, `docs/`, and `git log --grep`. The only Windows-related hits are unrelated (STATE.md:215-224 gate check; STATE.md:1181 MSYS path trap; tasks/todo.md:1149 WinError 32; docs/runbooks/token-renewal.md Windows runs of test_renew_token). STATE.md:222 points to `../tasks/windows-gate-verification-2026-09-12.md`, which lives outside this repo and was not available. The failing test names are therefore NOT VERIFIED from repo sources; the figure of 9 and the per-module split come from PR #1080 only.

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
0 failures reproduce on Linux; no product defect found; no code changed. Any Windows-side failures remain unreproduced here and are plausibly environment-only (CRLF in `.sh`/templates, path separators, bash availability; STATE.md:2064 records a CRLF/.sh incident), but that is an untested hypothesis (LOW confidence). Injecting CRLF into console.html, ci.yml, compose_resolved_check.py or entrypoint.sh does not fail these modules on Linux (independent reviewer, mutants 3, 4, 9, 10), which weakens the CRLF hypothesis for these files. Triage still needs the actual Windows failure output (test names plus first error lines); #1080 gives only counts.
