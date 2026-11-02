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

## 2026-11 hardening campaign (coordinator rules, each with its evidence file)

- **After a reviewer PASS, nobody pushes to that PR head.** → A push voids the
  verdict and the GX10 run, so a moving head never merges (one PR moved twice in
  an hour). → If more work is needed, open a new PR or wait for the merge; say in
  the note which gate a push resets. Exception: a fix for a condition of a PASS WITH
  CONDITIONS verdict, or a conflict the coordinator asked for. Evidence:
  `comms/inbox/builder/20261101-0731-coordinator-head-freeze-after-pass.md`,
  `comms/inbox/builder/20261102-1130-coordinator-freeze-pr431.md`.

- **A PR head that already contains main lands as a fast-forward, as it is.** → No
  rebase or squash is needed, and every rewrite resets CI and the verdict. → Check
  that the head holds main and that author and committer are the noreply identity;
  then the coordinator pushes that head. Evidence:
  `comms/inbox/builder/20261102-1300-coordinator-ruling-pr431-fast-forward-head.md`.

- **A batch branch with no PR has no CI run.** → The merge gate needs CI success on
  the exact head. → Open one draft PR from the batch head (batch note as the body, no
  estate values) and do not push to it afterwards. Evidence:
  `comms/inbox/builder/20261102-0600-coordinator-to-lane-r-open-draft-for-ci.md`.

- **docs/ENVIRONMENT.md anchor conflicts: take main's file, then regenerate.** →
  Hand-merging the anchor rows leaves wrong line numbers and a red test. → Take the
  main version, run `python tools/environment_anchors.py --fix`, then `--check`.
  Never merge main into someone else's PR for it. Evidence:
  `comms/inbox/builder/20261102-1130-coordinator-freeze-pr431.md`.

- **Two lanes on one card: the earliest claim by git commit time wins, the other
  withdraws.** → Double claims cost a whole PR of duplicate work (it happened on
  several cards). → Run `git grep -l -w <id> -- comms/inbox/coordinator` just before
  claiming, claim with one file, and where the coordinator names an owner, that owner
  keeps the card. Evidence:
  `comms/inbox/coordinator/20261101-0705-groomer-new-prs-416-417-c84-double-claim.md`,
  `comms/inbox/builder/20261102-1500-coordinator-c1127-c1128-c1129-owners.md`,
  `comms/inbox/coordinator/20261102-2010-builder-lane13-withdraw-c1197.md`.

- **"Contains main" is read from the run report, not assumed.** → A head can be
  green on 16 of 16 and still be built on a stale main. → Take the verdict from the
  GX10 report's own lines: head before and after the run, whether it contains the
  current main, and the identity check. Evidence:
  `comms/inbox/coordinator/20261103-2745-gx10-verifier-B-batch-s2q.md`.

- **A scrub keeps a placeholder default and an environment override for any
  deploy-gate rule.** → Replacing a string that a guard reads as a rule changes the
  deploy gate, not just the prose. → Default to the placeholder, read the real value
  from an environment variable documented in the module and in docs/ENVIRONMENT.md,
  and add fail-first tests (default, override, refused path, empty variable).
  Evidence: `comms/inbox/coordinator/20261102-2105-reviewer-q87.md`,
  `comms/inbox/builder/20261103-2500-coordinator-scrub-rulings-c1196-c1197.md`.

- **No estate value, flag value, build id or deploy status in any file, commit or PR
  text of the public repo.** → The repo is public; counts and classes are enough to
  prove a scrub. → Report counts, classes and file:line only, keep placeholders in
  the files, and run the scanner method before saying "clean". Evidence:
  `comms/inbox/builder/20261102-1600-coordinator-don-ruling-scrub-all-c1130-c1134.md`.
