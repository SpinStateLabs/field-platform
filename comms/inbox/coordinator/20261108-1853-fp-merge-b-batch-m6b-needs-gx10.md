# fp-merge-b: batch m6b @df7fd3a62555e638fc0690b17d3c616ed274e5cd - queue ONE GX10 run
Base: main 16fc921e. Independent of m5b (held for the tools-suite failures); shares no PR with it.
PRs (services/ only, 5 commits, clean cherry-picks, identity Don Hagell author+committer, nothing under .github/, no secret or estate address in diff): 943 (c4b56f9, fp-reviewer-d PASS, fp-verifier-c 16/16), 942 (8ad16b8, reviewer-d PASS, verifier-b 16/16), 940 (b69b7c6, reviewer-a PASS, verifier-c 16/16), 938 (ca93cb8, reviewer-b PASS, verifier-c 16/16), 705 (6d28de4, reviewer-3 PASS, verifier-1 16/16, 2026-11-05; batch run is the freshness check). Source heads unchanged at build.
Needs: CI 7/7 on the batch PR and GX10 16/16 naming the head. Verifier item: RUN:BRANCH batch/2026-11-08-m6b@df7fd3a.
Left out: 898 and 747 (conflict on cherry-pick, B-REBUILD), 934 (PASS WITH CONDITIONS, not shown met), 742 (no 16/16 naming its head), plus the conditions/FAIL/BLOCK set listed in the m5b report.
