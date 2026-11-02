# tasks/lessons.md

Generalized rules learned from corrections (rule → why → how to apply). Review at
session start. Append after any correction; keep each entry short.

- **Frame-check every number before it ships.** → A governance product that
  miscounts its own evidence has no standing; two self-caught errors already
  (attestation revoked-count, agent-estate 5× vs 6.4×). → After computing any
  figure for a doc/report/UI, recompute from source units before committing.

- **A word is Enforced only while a named test asserts it.** → The v2 one-liners claimed
  "continuously", "every agent", "OAuth for agents", "RACI-ready", none of which a test backed.
  → Cite `path::test_name` + commit for every Enforced word, run `tools/e_gate.py`, and
  reword to what the test proves. (Phase E, 2026-10-30.)

- **Meter and ledger the shadow path too.** → Don, 2026-09-13 ("meter those too"): a log-only
  ALLOW that is not metered lets a governed agent run uncounted. → Every ALLOW in either mode
  posts one spend row; test the shadow branches, not only enforce. (todo.md Phase D.)

- **Keep estate secrets separate.** → Don, 2026-10-05 (STATE.md): one shared key for both
  estates meant GB10 box access equalled Fly ledger append. → One secret per estate; never
  reuse across estates for convenience.

- **Build the Declared row instead of living with it.** → Don's instruction (todo.md, "make
  the five remaining components enforced instead of declared"; v1.2 "no more 'that's not
  working yet'"). → Treat a Declared row as a backlog item; where it cannot be built, state the
  reason in the row, never soften the wording.

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
