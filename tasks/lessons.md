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

- **A mismatch on an open service is a warning, not a refusal (C-467, D-21).** → Don ruled WARN (a log line plus a counter) for C-467, and a startup WARNING when a service starts open with the demo compose defaults kept, no refusal. → Add the warning and the counter; do not add a refusal unless a ruling says so.

- **The public repository holds no client names, rates or payment mailbox, and no large tracked media (C-561).** → Don ruled to remove client names, hourly rates and the payment mailbox from the invoicing agent's skill file and to untrack the capstone video; the sandbox's fly.dev hostname is meant to be public. → Keep such values out of the tree; a tracked build artefact is untracked, not rewritten.

- **Stop new bad commits and clean the tip; do not rewrite history (C-563).** → Don ruled option (c): a CI guard for new ones and a tip clean-up, NO history rewrite. → Propose guards and a tip fix; never a history rewrite or a branch-delete sweep without an approval (D-16 and D-25 were approved separately, for named heads).

- **Scrub, do not relocate, a runbook (C-606).** → Don ruled: home paths and the workstation name, build and release ids and dated deploy observations become placeholders; the runbook is not moved out of the repository. → Edit in place with placeholders.

- **Defer alert senders until the rotator is reworked (C-552).** → Don ruled to DEFER all six ntfy senders until PR 57 is reworked; docs say the test alert only. → Do not wire a sender early; keep the docs to what exists.

- **Keep a 5xx upstream body hidden from operators (PR 348).** → Don ruled it stays hidden. → Show the fixed phrase and the status, never the body.

- **Block, refuse or reject; do not tolerate (D-19, D-20, D-18).** → Don ruled: block keyless contracts now in the federation broker (replay binding deferred, D-19); refuse a catch-all (/0) allowlist in defence-shield (D-20); reject a verifier-scoped row that lacks the exact svc-verifier- prefix (D-18). → Implement the refusal where the ruling names it; defer only what it defers.

- **Keep halting (fail closed) until a reconcile exists (D-6).** → Don ruled KEEP halting until an R9 reconcile exists (C-29, the PR 57 rework). → Do not add an auto-resume.

- **Do not pin hashes before the build backend has soaked (C-478).** → Don ruled DEFER hash-pinned requirements until C-459 has soaked. → Leave the pins out until the soak is recorded.

- **A soak is shortened by an environment override for the run only (soak item 1).** → Don ruled to shorten the scheduler intervals for the 25-hour soak by environment override only, and for the PR 57 `_soak` 30 minutes with a single 24-hour soak at the very end. → Never edit the committed intervals to shorten a soak.

- **Keep merging invisible joiners and marks; document the collision (PR 322); the kill-switch guard keys on the path alone, as built.** → Don ruled both. → Do not split the merge or add a second guard key without a new ruling.

- **A held PR is reviewed, but Don decides the merge (PR 57).** → Don lifted the hold for a full reviewer pass and a GX10 run on the exact head, and kept the merge decision. → Review it; never merge it.

- **Keep the repository identity with the Co-Authored-By trailer (D-9, provisional).** → Don ruled to keep the Don Hagell identity with the trailer; his objection to a shared identity stays open. → Author and committer are the repository identity; the trailer names the agent.

- **Build the internal-only secret before Stage 2; per-agent secrets come later (D-12).** → Don ruled FIELD_INTERNAL_SECRET (the C-54 plan) is a Phase G Stage 2 prerequisite and per-agent secrets are deferred. → Do not build per-agent secrets in the Stage 2 work.
