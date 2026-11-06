# Review PR 825 (rebuild of 379: deploy runbook scrub, C-607) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `ec97988ec414dbb72b115118fefbfa91e1729e66`. Docs and one test string only.
Condition C1 (one-token condition fix): docs/runbooks/v1.2-deploy-rollback.md:1099 still reads "written against `56d63c3` plus PR #32", a commit id left in a public file while the PR title and body say the scrub is finished and replace every other such id (`8628814`, `1c14b52`, `db5ad33`) with `<build-id>`. Replace it (or the coordinator states it is accepted as a source commit, not a build id). Condition C2: the standard light CI (docs only) on the head.

## Objections first
1. The PR's claim "the scrub is finished" is false by one id (C1), and by out-of-scope files: `STATE.md:597`, `tasks/todo.md:234,244` still carry the ledger heads `1403fba4b898…`/`f262a7388680…`, `STATE.md:716` names `db5ad33`, `make_fixture.py` and `test_buildinfo.py` name `db5ad33` (the PR itself notes the test docstring). Not in this PR's file list, so not a defect of it, but the public-repo goal is not met repo-wide (HIGH, git grep run by me).
2. Nothing enforces the scrub (see mutants): a later edit can re-introduce a workstation name, a personal profile path or a build id and every test stays green; the previous round's last commit already re-introduced line cites that way.
3. Conflict resolutions (five in the runbook) went toward main's wording; the cherry-picks no longer match #379 by patch-id (all 4 differ, as expected after conflicts), so fidelity cannot be shown by patch-id; I read the whole net diff instead.

## Checks (HIGH, run by me)
- Identity: 5 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 5; trailers 4 x Sonnet 5.5, 1 none; no Fable. .github/: 0 files. Base == current main ede21674. Files: docs/runbooks/v1.2-deploy-rollback.md (+61/-57), tools/tests/test_deploy_docs.py (+1/-1: the section-anchor string follows the `<control-workstation>` rename).
- Whole net diff read (118 changed lines): replaces `rog-command` with `<control-workstation>`, `C:\Users\donal\...` with `%USERPROFILE%` / `os.path.expanduser`, dates/times/releases/build ids/ledger heads with placeholders, tags scripts that live outside the repo ("not in this repository"), and adds twice "A deploy needs Don's approval in chat before this section; do not start without it." Section 7 heading now says arming "needs Don's approval". No estate address, key or secret added (grep of the resulting runbook: no non-loopback IPv4; remaining `<gb10-lan-address>` placeholders pre-exist).
- Remaining sensitive tokens in the resulting runbook: only `56d63c3` (C1). No `rog-command`, no `donal`, no `C:\Users`, no `claude-session-scripts`.
- Line cites I checked against the head: `sealed_ledger/api.py:372-400` contains the `admit_ledger_event` call (lines 385-396): correct. `agent_registry/api.py:255-292` spans the owner/manifest_ref handling and the `assert_operator` exemption comment (277): consistent. (Line cites in the runbook are allowed; the lint only watches ARCHITECTURE.md and IMPLEMENTATION.md.)
- Tests (Windows, on the head): test_deploy_docs, test_docs_no_line_cites_sd1, test_environment_doc, test_environment_anchors_c1116: 135 passed; `environment_anchors --check`: 0 wrong rows.

## Reversal checks (the docs analogue of mutants; each applied alone to the runbook, tests: deploy_docs, no_line_cites, environment_doc; 99 tests; counted from the table)
| # | change | tests |
|---|---|---|
| L1 | `rog-command` reintroduced | still green (SURVIVED) |
| L2 | `C:\Users\donal\...` reintroduced | still green (SURVIVED) |
| L3 | build id reintroduced | NOT APPLIED (my search string did not match; no result) |
| L4 | ledger head reintroduced | NOT APPLIED (same) |
| L5 | approval sentence removed | still green (SURVIVED) |
| L6 | "not in this repository" tag removed | still green (SURVIVED) |
Totals: 6 attempted, 4 applied, 4 survived, 0 killed, 2 not applied (4+2 = 6). No test pins any of the scrub or the approval wording. Tree restored, clean.

## Optional follow-up (new PR)
A small lint over docs/runbooks and tests/ for the workstation name, personal paths and 7+ hex build ids, plus a sentence-pin for the approval line; scrub the out-of-scope files in item 1.

## Not verified
CI; Linux; GX10 (docs only); the other four runbook-related tools tests the PR cites (324 passed per the PR; I ran 135).
