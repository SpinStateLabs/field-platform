# READY: batch CA, PR 390 (draft). Not merged by the assistant.

- Head: acaf5f241f00754442c7adbbb0290769dbfe52c5 (sha7 acaf5f2), base main 5777030 (full 577703005a8a637f3db81153741956a490f1bdb0), branch batch/2026-11-06-ca.
- `git merge-base --is-ancestor origin/main origin/batch/2026-11-06-ca`: YES (fast-forward possible).
- Supersedes batch BZ (PR 386, based on old main 63e91b2; closing 386 is the coordinator's).

## Sources, cards, verdicts (all on the source head, which is unchanged at 20:10)
| Source PR | Head | Card, lane | Verdict | Conditions and why not blocking |
|---|---|---|---|---|
| PR 290 | 33b2c02 | C-447, Lane 7 | PASS WITH CONDITIONS | F-C447-1: "C0 every 15 minutes" left inside 5-minute soaks (tasks/todo.md:477, :624). Docs only; follow-up PR 382 (C-806). Non-blocking. |
| PR 319 | 34895a4 | C-593, Lane 6 | PASS | F-C593-1 LOW-MEDIUM: srcset rule needs a space after a comma, so `1x,https://...` forms pass the guard (old pattern caught them with false positives); F-C593-2 LOW: 3 surviving mutants. Guard coverage gap, no behaviour change on main; coordinator may want a follow-up card. |
| PR 328 | 7679259 | C-585, Lane 5 | PASS WITH CONDITIONS | (1) exit contract 0/2/3 on unexpected model shape and `--realpath` root; (2) scope text: does not close PR 329's F-C589-2 (build.dockerfile, unread keys); (3) pins. Hardening and text; follow-ups PRs 345, 353, 370, 385. PR 329 is CLOSED unmerged. |

## Patch-ids (git patch-id --stable): source = batch
| Source commit | Batch commit | patch-id |
|---|---|---|
| 33b2c023 (PR 290) | d0e52bc3 | 3ec6af8d8a90 |
| da0e9b42 (PR 319) | 78b6660a | b102acfad4d5 |
| fedacae3 (PR 319) | 8a16657f | f864680871e3 |
| 34895a47 (PR 319) | 9ad3fff2 | 064f543d5022 |
| 76792597 (PR 328) | acaf5f24 | f939689c8a21 |
Author and committer of all five: Don Hagell no-reply. Commits carry `-x` trailers.

## GX10 (run ca, exact head, fetched from GitHub; ca-all.done present)
16 "== " suites, 0 lines match failed|error. core+sealed-ledger 1924 passed 4 skipped; tools 3255 passed 4 skipped; field-agent 153; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353 (5 skipped); conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.

## CI on acaf5f2 (run 41143875408, pull_request): 7/7 SUCCESS
tests (3.11), (3.12), (3.13), (3.14), compose-smoke, fly-image-smoke, compose-upgrade-smoke.

## Merge (coordinator; PR 390 is still a draft, fast-forward as in BX/BY)
```
git fetch origin && git merge-base --is-ancestor origin/main acaf5f241f00754442c7adbbb0290769dbfe52c5 && git push origin acaf5f241f00754442c7adbbb0290769dbfe52c5:refs/heads/main
```
Re-check before running: main still 5777030 and PRs 290, 319, 328 heads unchanged. On merge: close PRs 290, 319, 328, 386, 390; PR 319 and 328 sources have no newer commits as of 20:10.

Generated with Claude Code
