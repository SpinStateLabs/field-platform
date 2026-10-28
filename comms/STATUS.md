# STATUS (coordinator-written)

Updated 2026-10-28. Integration head: main = origin/main = c8ecba7 (key rotation R1 #53, R2 #54, R3 #51 merged). `gb10` remote main = cefb81b (3 behind; HIGH).

| Branch / PR | Head | vs main | CI | Reviewer | GX10 | State |
|---|---|---|---|---|---|---|
| #57 feat/kr-r4a-rotator-core | 09dcbcd | +6/-0 | green | CONDITIONS (C-1) | GX10 green: 1653+1910 passed, 4+3 skipped | draft; no PASS, not mergeable |
| #55 feat/machine-verifier-identity | 6e78f31 | +8/-0 | green | CONDITIONS (C-2) | reviewer GX10 55 passed (exact head) | draft; fixes C-13 |
| #56 feat/alerts-ntfy | 9cdef89 | +2/-0 | green | CONDITIONS (C-6) | reviewer GX10 57 passed | draft; fix C-14 |
| teammate-don/t1-renew-token-signed | 1e67768 | +1/-0 | - | none | not run | no PR |
| feat/phase-g-check-tool | fb80a31 | +28/-4 | - | - | - | needs rebase |
| feat/c20-console-key-transport | fa95f96 | +5/-5 | - | - | - | needs rebase |

Running jobs: none by this coordinator. Blockers: no named teammates (D-3); no reviewer verdicts on record. Deploys: none authorised.

Poll 2026-10-28 08:45: C-1/C-2/C-6/C-9 DONE, none PASS, so no merge. ci/harden and ci/topology-lint already squash-merged (#16, #18): do not rebase. Open cards C-3..C-5, C-7, C-8, C-10, C-12..C-17. D-5 provisional, D-6 open.

Poll ~09:10: no new heads on #55 #56 #57; none mergeable. C-19 unblocked (fix/renew-token-signed). C-20, C-22 DONE. New cards C-26..C-29.

Poll ~09:25: C-19 CONDITIONS on fix/renew-token-signed (no PR, no CI); new cards C-30, C-31. #55 #56 #57 heads unchanged, none mergeable.

Poll ~09:50: C-27 PASS (real Caddy, 42 shapes, 0 bypasses). New cards C-32, C-33. #55 #56 #57 and fix/renew-token-signed heads unchanged; none mergeable.

Poll ~10:10: C-33 PASS. New card C-34. Builder has pushed nothing since assignment (about 1h): 17 open builder cards, no hand-backs; coordinator will message to ask for a status line. #55 #56 #57 unchanged; none mergeable.

Poll ~11:05: C-34 PASS with conditions: 2 MEDIUM on main (C-35, C-36 cards). Builder still silent. #55 #56 #57 unchanged, none mergeable. GB10 catch-up deploy held (D-11), needs Don approval anyway.

Poll ~11:20: C-16 read and C-17 mutants reported (CONDITIONS, no FAIL). New cards C-38, C-39. Reviewer did not use Workflow: the opt-in must come from Don in its own chat. Builder still silent. Heads unchanged, none mergeable.

Queue restocked ~11:45: C-40..C-44. Open: builder C-3,4,5,7,8,10,12,13,14,15,23,24,25,26,28,29,30,32,35,36,38,44; reviewer C-21,31,37,39,40,41,43; cloud C-18,42.

Queue restocked ~11:55: C-45..C-50.

Poll ~12:00: C-37 DONE (R1/R2 tests: 263/294 mutants killed; one design gap: a same-generation file can re-admit an evicted retired key). New card C-51. Reviewer commits carry author donhagell@gmail.com, not the repo identity (comms branch only; noted, not changed). Heads unchanged, none mergeable.

Poll ~12:20: C-3 and most of C-4 are moot: phase-g-check-tool is PR #28 (squash-merged), c20 branch is PR #50. C-39, C-40 DONE (one MEDIUM, C-52). Heads of #55 #56 #57 unchanged, none mergeable.

Poll ~13:20: C-41 (#48 MEDIUM proxy leak, #50 PASS) and C-48 (compose threat note) DONE. New cards C-53, C-54, C-55; D-12 open for Don. Heads unchanged, none mergeable.

Poll ~13:50: C-55 DONE: env-proxy class is estate-wide (59 httpx sites). GX10 check: no proxy vars. New cards C-56, C-57; D-13 provisional. Heads unchanged, none mergeable.

Poll ~14:30: C-58 (gateway key echo MEDIUM-LOW) and C-59 (claude-approver-v0 already PR 35) DONE. C-7 reassigned to reviewer (D-14). New C-60, C-61. Heads unchanged, none mergeable.

Poll ~14:55: C-61 triage DONE: of 53 unmerged-looking branches, 46 are squash-merged (PR tip equals branch tip), 3 closed and superseded, 3 open PRs (#55 #56 #57), 1 no PR (fix/renew-token-signed). Nothing abandoned. C-3, C-4 moot confirmed. C-62, C-63 queued; delete only with Don approval after C-63. Heads unchanged, none mergeable.

Poll ~15:35: C-62, C-63 DONE; delete script dry-run clean (49 would delete, 0 moved). Awaiting Don (D-15). Heads unchanged, none mergeable.

Poll ~15:45: no new hand-backs. Coordinator started a baseline GX10 run of main c8ecba7 in ~/ff-work/wt-main (logs main-core.log, main-tools.log, marker main.done). C-64, C-65 added for the reviewer. D-15 still awaiting Don. Heads unchanged, none mergeable.

Poll ~16:10: GX10 baseline of main c8ecba7 GREEN: core+sealed-ledger 1528 passed, 4 skipped; tools/tests 1882 passed, 3 skipped (HIGH; ~/ff-work/wt-main, logs main-core.log, main-tools.log). No new hand-backs; heads unchanged, none mergeable. D-15 awaits Don.

Poll ~16:25: C-64, C-65 DONE: #45 PASS with MEDIUM test gap (7 of 23 mutants survive), #46 PASS, #41 PASS with conditions, #44/#37/#39/#32 covered in the report. C-40 f5 withdrawn by reviewer. New C-66, C-67. Heads unchanged, none mergeable. D-15 awaits Don.

Queue restocked ~16:50 on Don's request: C-68..C-72. Open by role: builder C-4,5,8,10,12..15,23..26,28..30,32,35,36,38,44..47,51..54,56,57,60,66,68,69; reviewer C-21,31,43,67,70,71; cloud C-18,42,49,72.

Update ~17:20: D-15 DONE: 49 remote branches deleted (0 skipped), archive tag archive/pg-s0-guards. Origin has 12 heads. C-67 DONE (service suites green on main; reviewer harness bug fixed). New C-73. #55 #56 #57 heads unchanged, none mergeable.

Update ~17:50: Don: coordinator takes cards when idle. C-14 done at f657bea on #56 (local Windows 58 passed, 1 skipped; both new tests fail without the fix; GX10 run in ~/ff-work/wt-alerts, marker alerts.done). Coordinator now on C-35. #56 needs reviewer re-review, C-26 still open on the same branch.

Update ~18:45: coordinator took cards: C-14 (#56 now bebf0f1; reviewer C-43 found a test gap in f657bea, fixed) and C-35 (PR 58, 75a84c8). New cards C-75..C-77. C-71 DONE, C-74 DONE; D-16 awaits Don. #57 and #55 still unfixed (builder silent). GX10 run of #56 f657bea core: 1587 passed, 4 skipped (superseded head).

Poll ~19:00: no new hand-backs; reviewer working C-75, C-76. Heads: #56 bebf0f1, PR 58 75a84c8 (CI 2 pass, 5 pending, mergeable), #55 6e78f31, #57 09dcbcd, renew-token 8269445. Coordinator started GX10 runs on exact heads: wt-alerts2 (bebf0f1) and wt-bg (75a84c8), logs ~/ff-work/{alerts2,bg}-{core,tools}.log, markers alerts2.done, bg.done, script ~/ff-work/runhead.sh. Old f657bea run is superseded. None mergeable (no reviewer PASS yet). D-16 awaits Don.

Poll ~19:40: C-75 PASS (#56 bebf0f1, one LOW) and C-76 PASS (PR 58 75a84c8, one LOW). Both heads 0 behind main c8ecba7. GX10 (coordinator, exact heads): #56 core 1588 passed 4 skipped; PR 58 core 1532 passed 4 skipped; tools/tests running for both. Plan: merge PR 58 ff-only when its tools run and CI are green; #56 waits for C-77 (stage_aborted class). New cards C-78..C-80.

MERGE ~20:15: PR 58 / C-35 fast-forwarded into main: c8ecba7 -> 75a84c8 (1 commit, author and committer Don Hagell noreply). Evidence: reviewer C-76 PASS on 75a84c8, CI tests 3.11-3.14 + compose-smoke + compose-upgrade-smoke + fly-image-smoke all pass, GX10 coordinator run on the exact head: field-core+sealed-ledger 1532 passed 4 skipped, tools/tests 1882 passed 3 skipped. Not deployed. Others now 1 behind main: #56 bebf0f1, #55 6e78f31, #57 09dcbcd, renew-token 8269445: rebase and re-run GX10 before any merge. Coordinator now on C-77 (stage_aborted class on #56). C-80 (reviewer post-merge check) is live.

Update ~20:50: #56 could not be fast-forwarded after PR 58 landed and a force-push is not allowed, so the coordinator rebased it onto main 75a84c8 (all commits re-authored with the repo identity) and pushed feat/alerts-ntfy-r2 @c6883e5 as draft PR 59, with the C-77 commit (stage_aborted, rotation_halted). Local 61 passed, 1 skipped. GX10 run on the exact head in ~/ff-work/wt-r2 (marker r2.done). Reviewer card C-81. PR 56 stays open until PR 59 merges. Auto-fix on for PR 59.

Update ~21:20: coordinator took C-36: PR 60 (fix/observer-witness-content-edit @c71c8be): the observer witness now sees content-only edits (sha prefix in the change key); local observer r2+c6 55 passed, mutant (sha removed) red; GX10 run in ~/ff-work/wt-obs (marker obs.done). Reviewer card C-82. PR 59 (alerts r2 @c6883e5): GX10 core 1594 passed 4 skipped, tools running; CI tests pending; awaiting reviewer C-81. main 75a84c8.

Update ~21:30: C-81 DONE: PR 59 (alerts r2 @c6883e5) PASS with one LOW on the reviewer side (range-diff against #56: only the author line and the C-77 commit differ). Merge waits on my GX10 tools run on the exact head (r2.done) and CI tests 3.11-3.14. Then close PR 56 as superseded. New card C-84.

MERGE ~22:10: PR 59 / C-14 + C-77 fast-forwarded into main: 75a84c8 -> c6883e5 (5 commits, all author+committer Don Hagell noreply). Evidence: reviewer C-81 PASS on c6883e5, CI 7/7 green, GX10 exact head: core+sealed-ledger 1594 passed 4 skipped, tools/tests 1882 passed 3 skipped. Not deployed. PR 56 is superseded but STILL OPEN: the auto-mode classifier blocked my attempt to close it with a comment (external write); needs Don or his OK. PR 60 superseded by PR 61 (rebased onto c6883e5 + docstring); GX10 run in ~/ff-work/wt-obs2 (marker obs2.done); reviewer card C-85. C-80 PASS: main 75a84c8 fully green on the reviewer GX10 run. Alias squat (C-78) still open.

Update ~22:40: coordinator took C-78: PR 62 (fix/breakglass-alias-squat @10fa36c, on main c6883e5): format-2 files with the don-breakglass alias on any other row are refused; local 318 passed; mutant red; GX10 run in ~/ff-work/wt-alias (marker alias.done); reviewer card C-86. PR 61 (C-36 r2 @aaae5ec): GX10 core 1596 passed 4 skipped, tools running; CI tests pending; awaiting reviewer C-85. PR 56 still open (close blocked by the classifier; Don asked).

Poll ~23:00: reviewer PASS: C-85 PR 61 (aaae5ec) and C-86 PR 62 (10fa36c, one LOW: format 1 still accepts the alias squat; not a blocker, C-87). Both need green CI tests (pending) and my GX10 tools run on the exact head (core 1596 passed 4 skipped for each; tools running) before a ff merge. main c6883e5.

MERGE ~23:20: PR 61 / C-36 fast-forwarded into main: c6883e5 -> aaae5ec (2 commits, Don Hagell noreply). Evidence: reviewer C-85 PASS, CI 7/7, GX10 exact head core+sealed-ledger 1596 passed 4 skipped, tools/tests 1882 passed 3 skipped. Not deployed. PR 62 now 1 behind: rebased as PR 63 (fix/breakglass-alias-squat-r2 @84d26a4, patch unchanged), local 318 passed, GX10 run in wt-alias2 (marker alias2.done); reviewer card C-89; old PR 62 stays open like PR 56 (closing needs Don).

Poll ~23:45: reviewer C-89 PASS on PR 63 (84d26a4, same patch as PR 62). GX10 core 1598 passed 4 skipped; tools/tests and CI tests (3.11-3.14) pending. Merge ff when both green. main aaae5ec.

MERGE ~00:20: PR 63 / C-78 fast-forwarded into main: aaae5ec -> 84d26a4 (1 commit, Don Hagell noreply). Evidence: reviewer C-89 PASS, CI 7/7, GX10 exact head core+sealed-ledger 1598 passed 4 skipped, tools/tests 1882 passed 3 skipped. Not deployed. PR 62 and PR 56 remain open (closing needs Don). Coordinator now on C-87 (format-1 alias rule in validate_rows).

Update ~00:50: coordinator took C-87: PR 64 (fix/breakglass-alias-format1 @a8bd47c, on main 84d26a4): the break-glass alias rule now in validate_rows (format 1 too); local 379 passed; mutant red; GX10 run in ~/ff-work/wt-f1 (marker f1.done); reviewer card C-90.

PR 56 CLOSED ~01:00 at Don's instruction (superseded by PR 59, merged as c6883e5). PR 62 (superseded by PR 63, merged as 84d26a4) is still open; Don has not yet said to close it.

Update ~01:15: Don gave close authorization: PR 56, PR 62, PR 60 closed (all superseded by merged PRs 59, 63, 61). Open PRs now: 64 (C-87, review C-90), 57, 55. Coordinator took C-52. Queue restocked: C-91..C-94.

Update ~01:35: the 5-minute poll (job d2d9f8f9) also restocks the queue each fire; Don asked for that again. Coordinator took C-52: PR 65 (fix/refused-record-drop-counted @5ddabeb): note_refused counts a refusal with no ledger as dropped; local 58 passed; mutant red; GX10 run wt-ref (marker ref.done); reviewer card C-95. PR 64 (C-87) still waiting on reviewer C-90 and CI.

Poll ~01:40: reviewer C-90 PASS on PR 64 (a8bd47c, C-87): 4 of 4 mutants killed, R4a migration (#57) fails clearly and leaves the file byte-identical on a format-1 file that fails the rule. One rollout LOW (see report). PR 64 now needs CI tests (3.11-3.14, pending) and my GX10 tools run (core 1600 passed 4 skipped; tools running). Then ff merge.

Poll ~02:00: reviewer C-92 DONE: GB10 pre-deploy checklist for main 84d26a4 (inbox/coordinator/20261028-2230-*). Key points: cefb81b..84d26a4 is 12 commits, 25 files, no compose/Dockerfile/manifest/volume change, every service image rebuilds (field-core), proxy needs --force-recreate; the real diff is from the DEPLOYED build_sha, not cefb81b (unknown from the repo; read-only estate_probe health on the GX10 would show it); check the live operators files for the don-breakglass alias before PR 64 lands. No deploy without Don approval; D-11 hold stands. PR 64 and PR 65 wait on CI and GX10 tools runs.

Poll ~02:20: C-95 PASS on PR 65 (5ddabeb). PR 64 (a8bd47c): reviewer PASS, GX10 exact head core 1600+4 skipped, tools 1882+3 skipped, CI tests pending. PR 65: GX10 core 1601+4 skipped, tools running, CI tests pending. No merge this poll.

MERGE ~02:50: PR 64 / C-87 fast-forwarded into main: 84d26a4 -> a8bd47c (1 commit, Don Hagell noreply). Evidence: reviewer C-90 PASS, CI 7/7, GX10 exact head core+sealed-ledger 1600 passed 4 skipped, tools/tests 1882 passed 3 skipped. Not deployed; before any deploy check the live operators files for the don-breakglass alias on a non-break-glass row (C-90 rollout LOW, C-92 B.3). PR 65 now 1 behind; rebase under a new branch name pending. Don 02:50: loop runs until the work is finished, then stand by checking every 1 minute: cron jobs replaced by one 1-minute job.

Update ~02:55: PR 65 went 1 behind after PR 64 merged; rebased as PR 66 (a91b819, patch unchanged), local 58 passed, GX10 run in wt-ref2 (ref2.done), reviewer card C-99. Coordinator took C-96 (console clickjacking headers).

Update ~03:25: PR 66 (C-52 rebased, a91b819): GX10 run wt-ref2 in progress, reviewer C-99. Coordinator took C-96: PR 67 (fix/console-frame-headers @079f587): console catch-all headers X-Frame-Options DENY, frame-ancestors none, nosniff in the base and Fly Caddyfiles; 11 static tests; existing edge tests pass; real caddy:2-alpine validate OK on both files; GX10 run wt-hdr (hdr.done); reviewer C-100. The commit message of 079f587 says 12 tests; 11 is correct (stated in the PR body).

Update ~03:35: reviewer C-99 PASS (PR 66 a91b819), C-91 remainder PASS (#25 LOW) and R-05 console.html PASS (LOW). PR 66: GX10 core 1603 passed 4 skipped, tools running, CI pending. Reviewer is self-serving from BACKLOG (R-01..R-06 claimed): the self-serve rule works. Coordinator took C-53.

Update ~04:20: coordinator took C-53: PR 68 (fix/fieldclient-no-env-proxy @23a1b81): FieldClient empty ProxyHandler plus 64 KiB bounded read; 5 new tests, both changes red when reverted; field-agent suite 118 passed locally; GX10 runs in wt-fc. Reviewer card C-102. PR 66 and 67 wait on GX10 tools runs and CI.

Update ~05:05: reviewer C-100 CONDITIONS on PR 67: it broke test_gb10_caddy_tls (the parser rejected header blocks); I ran the wrong tests, the reviewer caught it before merge. Fixed at 4921611 (parser accepts exactly the console frame-header block; 3 mutants); local 85 passed; GX10 run wt-hdr2 (hdr2.done); reviewer card C-103. PR 68 (field-agent): GX10 agent suite 118 passed on the exact head; core+tools running; CI pending; C-102 pending. PR 66: reviewer PASS, GX10 tools and CI pending.

Update ~06:00: coordinator took C-60: PR 69 (fix/gateway-key-hygiene @f312691): scrub the upstream key from replies, warn on plain http non-private base, judge errors name the class only; 13 new tests; 5 mutants red; GX10 runs in wt-gw; reviewer C-104; D-17 provisional. PR 66 reviewer PASS + GX10 exact head green, CI pending; PR 67 fixed at 4921611, C-103; PR 68 C-102.
