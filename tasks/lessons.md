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
  at `<home>\.venvs\field-platform`.

- **Never claim compliance/certification.** → It is the worst failure a governance
  product can make. → Crosswalk stays suggestion-only behind human sign-off; only
  cite verified regulatory dates (OSFI E-23 May 2027; EU AI Act post-Omnibus dates).

- **Measure changelog drift with `git log --since=<last entry date>`, not by reading the file.** → The CHANGELOG stopped at 2026-10-29 while 110 commits followed; reading the file alone hides this. → Each docs pass: count commits since the newest CHANGELOG date, then summarize them from commit subjects only (cite ids, no inference).

- **`grep` on `STATE.md` needs `-a`.** → It contains non-UTF-8 bytes and grep reports "binary file matches". → Use `grep -a` or the Grep tool when searching it.

- **Read `origin/comms` (PROTOCOL.md, ROLE-LOOP.md) before any PR action.** → Process rules live on the `comms` branch, not in main: only the coordinator merges; a merge needs an independent reviewer PASS and a GX10 run on the exact head; work is claimed through `comms/tools/dispatch.sh`. A docs session merged PR 520 on Don's chat instruction without either (2026-11-04) and had to report it. → At session start run `git fetch origin comms` and read both files; before merging, check `comms/locks/` for a reviewer lock on the PR; when the principal orders a merge that skips the path, do it only on an explicit instruction and report it to `comms/inbox/coordinator/` the same hour.

- **A squash-merged branch looks unmerged; do not rebase it.** → Its commits are not
  ancestors of `main`, so `git branch --no-merged` lists it, and rebasing it replays
  old edits over newer ones and can undo them (ci/topology-lint, C-9). → Before
  touching a branch that "has not merged", compare its PR tip with the branch tip
  (the PR page or the API shows the PR head); if the PR is merged, leave the branch alone.

- **Check author and committer identity before the first push.** → A commit written
  with an empty committer email had to be recommitted (D-9). → Run
  `git log -1 --format='%an <%ae> | %cn <%ce>'` before pushing and fix both halves: the
  repository identity is `Don Hagell <13129187+dhagell@users.noreply.github.com>` for author
  and committer; the Co-Authored-By trailer is the only trace of the agent.

- **In a venv, `sys._base_executable` is the system Python, not the venv's.** → A test
  that spawned it ran the tool without the venv's packages (no pydantic), so the signing
  tests failed on the GX10 and passed in a differently set-up CI (C-19, C-30). → A child
  that needs the platform packages is spawned with `sys.executable`; use
  `sys._base_executable` only when the bare base Python is wanted on purpose.

- **Review parsers with truncated and malformed input, not only well-formed variants.** →
  A PASS missed that `fly_snapshot.py` fell back to an inner JSON fragment, so a truncated
  list passed a deploy gate with rc 0 (PR 1090; a second reviewer found it; 2026-11-21). →
  For any parser or gate, probe a truncated outer value, duplicated keys, and a valid
  fragment inside log noise; each must fail closed.

- **A mutant harness must prove it edited the intended function.** → Identical lines in
  `_internal_host` and `is_loopback_base` made a string-replace harness mutate the wrong
  function (PR 1084; 2026-11-21). → Anchor each mutant to a unique span and assert exactly
  one replacement inside that function.

- **Fetch origin/main fresh before stating a PR's base is current; quote both shas.** →
  The PR 1084 re-review stated a stale base (2026-11-21). → Run `git fetch origin main`
  first, then quote the PR base sha and the fresh `origin/main` sha in the review.

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
- **Before caching a function's result, trace every file the function reads, not just its
  arguments.** → T7 keyed the `/verify` cache on the layout and the live segments' bytes and
  called the result a pure function of them; `Snapshot._verify_archived` also reads archive
  copies, so an altered or deleted archive copy was answered `ok` from the cache (found in the
  T7 post-merge review, fixed by T8 #1078). → Read the whole call tree for file reads before
  claiming purity, and write one tamper test per file it reads, including archived and
  rotated layouts.

- **In the dossier, cite a paragraph by its heading, never by position, and write only what a
  source shows.** → Review of #1079 found "first paragraph" pointing at the second paragraph,
  timings cited to a README that does not hold them, and "on Don's chat instruction", which no
  file records. → Cite `"<heading>" paragraph` or a symbol, cite the artefact that actually
  holds each number (PR body, commit, file), and reword anything unsourced to what the source
  shows (e.g. "no reviews recorded").

- **A mismatch on an open service is a warning, not a refusal (C-467, D-21).** → Don ruled WARN (a log line plus a counter) for C-467, and a startup WARNING when a service starts open with the demo compose defaults kept, no refusal. → Add the warning and the counter; do not add a refusal unless a ruling says so.

- **The public repository holds no client names, rates or payment mailbox, and no large tracked media (C-561).** → Don ruled to remove client names, hourly rates and the payment mailbox from the invoicing agent's skill file and to untrack the capstone video; the sandbox's fly.dev hostname is meant to be public. → Keep such values out of the tree; a tracked build artefact is untracked, not rewritten.

- **Stop new bad commits and clean the tip; do not rewrite history (C-563).** → Don ruled option (c): a CI guard for new ones and a tip clean-up, NO history rewrite. → Propose guards and a tip fix; never a history rewrite or a branch-delete sweep without an approval (D-16 and D-25 were approved separately, for named heads).

- **Scrub, do not relocate, a runbook (C-606).** → Don ruled: home paths and the workstation name, build and release ids and dated deploy observations become placeholders; the runbook is not moved out of the repository. → Edit in place with placeholders.

- **Alert senders: the C-552 deferral is lifted; the six are on main (C-552, G23).** → Don ruled to DEFER them on 2026-10-31 and lifted that on 2026-11-05; the six ntfy senders are on main (fd0ac135, G23). The three rotation senders have no caller until PR 57 is reworked (C-496). → Do not wire a rotation sender before that rework; do not remove or re-defer the six.

- **Keep a 5xx upstream body hidden from operators (PR 348).** → Don ruled it stays hidden. → Show the fixed phrase and the status, never the body.

- **Block, refuse or reject; do not tolerate (D-19, D-20, D-18).** → Don ruled: block keyless contracts now in the federation broker (replay binding deferred, D-19); refuse a catch-all (/0) allowlist in defence-shield (D-20); reject a verifier-scoped row that lacks the exact svc-verifier- prefix (D-18). → Implement the refusal where the ruling names it; defer only what it defers.

- **Keep halting (fail closed) until a reconcile exists (D-6).** → Don ruled KEEP halting until an R9 reconcile exists (C-29, the PR 57 rework). → Do not add an auto-resume.

- **Do not pin hashes before the build backend has soaked (C-478).** → Don ruled DEFER hash-pinned requirements until C-459 has soaked. → Leave the pins out until the soak is recorded.

- **A soak is shortened by an environment override for the run only (soak item 1).** → Don ruled to shorten the scheduler intervals for the 25-hour soak by environment override only, and for the PR 57 `_soak` 30 minutes with a single 24-hour soak at the very end. → Never edit the committed intervals to shorten a soak.

- **Keep merging invisible joiners and marks; document the collision (PR 322); the kill-switch guard keys on the path alone, as built.** → Don ruled both. → Do not split the merge or add a second guard key without a new ruling.

- **Contract writes stay fail-open when the ledger is down (PR 395, C-553).** → Don ruled FAIL-OPEN, with the gap counted on /health and only the exception type in the log. → Do not make a contract write fail closed on a ledger outage.

- **Keep the 2027-01-31 removal date on the deprecated helper (PR 325).** → Don ruled keep the date, with a floor test only. → Do not move the date or add a ceiling test.

- **The CLI print sites keep printing exception text to an operator terminal (C-504).** → Don ruled to leave them (lifecycle-manager and ops-console cli.py). → Do not scrub them under a no-echo sweep.

- **Operator log-only is not an open service (PR 383).** → Don ruled the startup warning carries no operator line for log-only mode. → Add no operator line.

- **Keep the federation BLOCK-reason relay; cap the SDK read (PR 372).** → Don ruled keep the relay and add a size cap on the SDK transport read. → Do not remove the relay.

- **The four proxy-environment clients wait for C-487 (PR 381, PR 365).** → Don ruled WAIT. → Do not change them before C-487 lands.

- **A held PR is reviewed, but Don decides the merge (PR 57).** → Don lifted the hold for a full reviewer pass and a GX10 run on the exact head, and kept the merge decision. → Review it; never merge it.

- **Keep the repository identity with the Co-Authored-By trailer (D-9, provisional).** → Don ruled to keep the Don Hagell identity with the trailer; his objection to a shared identity stays open. → Author and committer are the repository identity; the trailer names the agent.

- **Build the internal-only secret before Stage 2; per-agent secrets come later (D-12).** → Don ruled FIELD_INTERNAL_SECRET (the C-54 plan) is a Phase G Stage 2 prerequisite and per-agent secrets are deferred. → Do not build per-agent secrets in the Stage 2 work.
