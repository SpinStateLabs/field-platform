# tasks/lessons.md

Generalized rules learned from corrections (rule → why → how to apply). Review at
session start. Append after any correction; keep each entry short.

- **Frame-check every number before it ships.** → A governance product that
  miscounts its own evidence has no standing; two self-caught errors already
  (attestation revoked-count, agent-estate 5× vs 6.4×). → After computing any
  figure for a doc/report/UI, recompute from source units before committing.

- **Per-service tests need `python -m pytest`, not bare `pytest`.** → Services whose
  tests import `tests.conftest` require the service CWD on `sys.path`; bare pytest
  broke CI run #1. → In CI and docs, run per-service suites as
  `(cd services/<s> && python -m pytest -q tests)`.

- **Windows/Drive gotchas.** → cp1252 consoles mangle ✓/✗ and em-dashes; SQLite +
  Google-Drive sync fight. → CLIs force UTF-8 stdout; the venv lives OUTSIDE Drive
  at `C:\Users\donal\.venvs\field-platform`.

- **Never claim compliance/certification.** → It is the worst failure a governance
  product can make. → Crosswalk stays suggestion-only behind human sign-off; only
  cite verified regulatory dates (OSFI E-23 May 2027; EU AI Act post-Omnibus dates).

- **Measure changelog drift with `git log --since=<last entry date>`, not by reading the file.** → The CHANGELOG stopped at 2026-10-29 while 110 commits followed; reading the file alone hides this. → Each docs pass: count commits since the newest CHANGELOG date, then summarize them from commit subjects only (cite ids, no inference).

- **`grep` on `STATE.md` needs `-a`.** → It contains non-UTF-8 bytes and grep reports "binary file matches". → Use `grep -a` or the Grep tool when searching it.

- **Read `origin/comms` (PROTOCOL.md, ROLE-LOOP.md) before any PR action.** → Process rules live on the `comms` branch, not in main: only the coordinator merges; a merge needs an independent reviewer PASS and a GX10 run on the exact head; work is claimed through `comms/tools/dispatch.sh`. A docs session merged PR 520 on Don's chat instruction without either (2026-11-04) and had to report it. → At session start run `git fetch origin comms` and read both files; before merging, check `comms/locks/` for a reviewer lock on the PR; when the principal orders a merge that skips the path, do it only on an explicit instruction and report it to `comms/inbox/coordinator/` the same hour.
