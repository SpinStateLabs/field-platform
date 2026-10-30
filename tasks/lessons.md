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

- **A squash-merged branch looks unmerged; do not rebase it.** → Its commits are not
  ancestors of `main`, so `git branch --no-merged` lists it, and rebasing it replays
  old edits over newer ones and can undo them (ci/topology-lint, C-9). → Before
  touching a branch that "has not merged", compare its PR tip with the branch tip
  (`gh pr view`); if the PR is merged, leave the branch alone.

- **Check author and committer identity before the first push.** → A commit written
  with an empty committer email had to be recommitted (D-9). → Run
  `git log -1 --format='%an <%ae> | %cn <%ce>'` before pushing and fix both halves;
  the Co-Authored-By trailer is the only trace of the agent.

- **In a venv, `sys._base_executable` is the system Python, not the venv's.** → A test
  that spawned it ran the tool without the venv's packages (no pydantic), so the signing
  tests failed on the GX10 and passed in a differently set-up CI (C-19, C-30). → A child
  that needs the platform packages is spawned with `sys.executable`; use
  `sys._base_executable` only when the bare base Python is wanted on purpose.
