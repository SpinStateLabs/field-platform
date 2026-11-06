ssl-ff-reviewer-9: reviewer queue EMPTY again (dispatch.sh next reviewer, exit 3). Round 2 summary (everything since the restock of 2026-11-06). Windows only, no GX10, no CI read: the GX10 gate is open on every head below.

| item | head | verdict | main points |
|------|------|---------|-------------|
| PR 750 | a5330d3a | PASS WITH CONDITIONS | 3 reviewer-3 findings fixed; merge conflict with main in docs/ENVIRONMENT.md (rerun anchors --fix at merge) |
| PR 851 | 025b58c4 | PASS WITH CONDITIONS | net diff = PR 797 minus ci.yml plus 4 allowlist lines; 17 of 19 guard mutants killed (2 by design); Don's ci.yml comment decision |
| PR 707 | 4c81fa61 | PASS | 7 doc survivors now killed |
| PR 822 | 117469db | PASS WITH CONDITIONS | batch m6 vehicle: 5 of 5 commits patch-identical to their PASS heads; 12 of 12 spot mutants |
| PR 788 | f29b6fab | PASS | deep-pack RecursionError fixed |
| PR 854 | faaab269, then 2fef9a2c | PASS WITH CONDITIONS, then PASS | a health test that could not fail; fixed on the second head |
| PR 665 | 030f5c5d | PASS WITH CONDITIONS | half-written pack on a second-write failure; lone-surrogate org crashes the CLI |
| PR 685 | ea1e59c5 | PASS | NUL condition fixed, 14 of 14 non-equivalent mutants |
| PR 651 | 40d3fdb0 | PASS WITH CONDITIONS | code conditions met; head red on test_environment_doc (3 anchors) and conflicts with main: rebase plus anchors --fix required |
| PR 857 | 8260a425 | PASS WITH CONDITIONS | BLOCK items of PR 541 fixed; the provisioning tool's default now also provisions five draft agents; --only untested; stale environment id in 5 manifests; key_intake.ps1 notes |
| PR 508 | d0873b0a | PASS | rebase condition met; deep-nesting traceback and unbounded n8n_export measured |
| PR 506 | a628fbbe | PASS | 0 mismatches vs a Decimal reference over 2.95 million amounts; one-to-two-cent boundary untested |
| PR 511 | 3675644c | PASS WITH CONDITIONS | blank-owner rule still bypassable with 17 other invisible characters; domain halt misses 5 spellings |
| R-RT-HARD-4 | main 250154d3f | NO BLOCKER; 2 MEDIUM, 3 LOW | heartbeat unbounded rows; registry manifest_ref 422 echoes caller text and the manifest directory |

Totals counted from the table, by final verdict: 14 rows = 6 PASS (707, 788, 854, 685, 508, 506) + 7 PASS WITH CONDITIONS (750, 851, 822, 665, 651, 857, 511) + 1 red-team verdict; 0 BLOCK. PR 854 produced two reports (its first head was PASS WITH CONDITIONS), so 15 reports in all.

Notes for the coordinator
1. Required fixes I would card first: PR 651 (anchors, rebase), PR 857 (provisioning default), PR 665 (half-written pack, surrogate org), PR 511 (blank owner rule), and from the red-team card F1 (heartbeat) and F2 (manifest_ref echo).
2. dispatch.sh next took about 25 s today; it took minutes under load earlier.
3. Scratch checkouts under D:/dev-cache/wt-rev9-pr* that could not be removed earlier (Permission denied) may still exist; they are mine and safe to delete.
