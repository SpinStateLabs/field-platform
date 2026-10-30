# C-677: read of PR 346 (commit-identity guard), Lane 10

Read: PR 346 tip 6e4a9d1 (the card names fb9dc61; the branch has a second commit that wires the guard into CI, so I read both): tools/check_commit_identity.py, tools/tests/test_check_commit_identity_c564.py, tools/tests/test_ci_commit_identity_job_c564.py, `.github/workflows/ci.yml` (+28, a `commit-identity` job). Read-only; UNVERIFIED on any estate. Probe: 20261104-0700-design-c677-commit-identity-probe-test.py (made-up identities only; `GUARD=<checkout>/tools python -m pytest -q`).

VERDICT: the guard does what it states for the four fields it reads (65 PR tests pass), prints only a short SHA and a field class, never a value (checked), and blocks no legitimate human commit. It has three structural blind spots and one false-positive class, all by what it does not read. Confidence HIGH (run).

## ASSUMPTIONS
1. Goal: no personal mailbox in a public commit's author or committer name or email.
2. The CI job runs only on `pull_request`; the workflow triggers are `push` to main and `pull_request`.

## Objections first (failure conditions)
1. It reads `%an %ae %cn %ce` only (LOG_FORMAT, check_commit_identity.py): a personal address in a `Co-authored-by:` or `Signed-off-by:` trailer, or free text in the message body, is never seen, and those are public too. Probe: the format string holds no `%b`/`%B`. A Claude session or a DCO flow writes exactly such trailers. MEDIUM. HIGH that it is unread.
2. Coverage by event: the job runs on pull requests only. A push to any branch that is not a PR, including the public `comms` branch (where every lane commits its notes), and a direct push to main are never checked; GitHub's squash or rebase merge also builds the merge commit's identity from account settings after the check ran. MEDIUM.
3. False positives: GitHub bot identities carry brackets in the handle (`<digits>+dependabot[bot]@users.noreply.github.com`, `github-actions[bot]`, `renovate[bot]`) and the accepted pattern `[A-Za-z0-9][A-Za-z0-9-]*` has no bracket: all three are BLOCKED (probe red, 3). A no-reply address in upper case is blocked too (2 red; GitHub emits lower case, so rare). The repository has no bot PR today as far as I can see; if one is added the job fails for a reason that is not a leak. LOW-MEDIUM.
4. Name spellings: an address written as a name in a form other than `text@text` passes: `zed at gmail dot com`, `zed (at) gmail.com`, `zed [at] gmail.com`, a full-width at-sign, `zed @ gmail.com` with spaces, `zed%40gmail.com`, `zed&#64;gmail.com` (7 probe cases, all accepted). The realistic leak is the plain form, which is caught; these need an author who obfuscates on purpose. LOW.
5. The `--allow-domain` escape hatch exists (`COMMIT_IDENTITY_ALLOW_DOMAIN`, a repository variable, none built in): any address under it passes, which is the point; its value is a company domain, not a secret, and `fullmatch` rejects `x@domain.evil`. A real personal name (not an address) as author is not a violation by this guard. LOW.
Steelman: it reads only the new range (`origin/<base>..<head sha>`), fails closed on a git error (exit 2), and the output discipline (SHA prefix, field, reason; no value in the stderr message or the `RuntimeError`/`ValueError` texts) is exactly what a public CI log needs: my probe confirms the finding strings contain neither the name nor the address.

## Results
- Accepted forms behave: `<digits>+<handle>@users.noreply.github.com`, `<handle>@users.noreply.github.com`, `noreply@github.com`, `noreply@anthropic.com`. Blocked: a gmail address, an example.com address, `...@users.noreply.github.com.evil.test`, `users-noreply...`, `noreply.github.com` as a host, a plus-tagged mailbox, an empty email, `googlemail`. Name field: `zed@gmail.com`, `<zed@gmail.com>`, `zed@x` blocked; "Don Hagell", "Claude", "dependabot[bot]", "GitHub" fine. Committer and author are checked independently.
- Output: findings print `<12-char sha>: <field> <reason>`; no value. Error paths print fixed texts.
- Mutants of mine: `fullmatch` to `match` (2 red); name check disabled (8 red); author email unchecked (11 red); committer email unchecked (3 red). SURVIVOR: the anthropic form loosened to a prefix (`noreply@anthropic.com.*`) stays green (36 passed): no test pins `noreply@anthropic.com.evil.test`. LOW-MEDIUM.
- The CI job: pinned checkout (a commit SHA), `persist-credentials: false`, `fetch-depth: 0`, `contents: read`, the range built from `github.base_ref` and `github.event.pull_request.head.sha` passed through `env` (not interpolated into the script: no injection), standard library only. A fork PR whose head sha is not in the base repository's history would make `git log` fail (exit 2, job red): acceptable, no fork PRs seen.
- Tests: 65 passed on the tip. Whole tools suite not run to green here.

## Findings
F-C677-1 MEDIUM: read the message trailers: add `%(trailers:key=Co-authored-by,valueonly)` and `Signed-off-by` (or `%B`) to the log format and apply the same address rules to the addresses inside them; print the class, not the value.
F-C677-2 MEDIUM: also run on `push` to branches other than main (at least `comms`), or document that comms commits are unchecked and make the lane rule (author and committer set to the repository identity) the control for them.
F-C677-3 LOW-MEDIUM: accept `<digits>+<handle>[bot]@users.noreply.github.com` (add `\[bot\]` to the handle class) and lower-case the email before matching.
F-C677-4 LOW-MEDIUM: pin lookalike domains for every accepted form, including `noreply@anthropic.com.evil.test`.
F-C677-5 LOW: widen `_EMAIL_AS_NAME` to catch the spaced and entity spellings, or accept that deliberate obfuscation is out of scope and say so in the docstring.

## What I did NOT do
Did not run the workflow or read an Actions run. Did not test a squash-merge identity. Did not check history (the guard does not either). Did not print any real identity. Did not edit the PR.
