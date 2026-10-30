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

- **A word is Enforced only if a test asserts it.** → A cited test that merely exists can name
  the wrong thing; the audit's old one-liners overclaimed this way. → Cite `path::test_name` + commit,
  run `python tools/phase_e_gate.py`, then read the test body for the cited word.

- **A quoted number needs its method and sha.** → Two totals for the same suite (7,267 at 3287f03,
  8,172 at 48acfa6) differ by about 900 with no explanation. → Write "collected, not passed", the command and the commit
  beside every count, and say when it does not reproduce.

- **Never claim compliance/certification.** → It is the worst failure a governance
  product can make. → Crosswalk stays suggestion-only behind human sign-off; only
  cite verified regulatory dates (OSFI E-23 May 2027; EU AI Act post-Omnibus dates).
