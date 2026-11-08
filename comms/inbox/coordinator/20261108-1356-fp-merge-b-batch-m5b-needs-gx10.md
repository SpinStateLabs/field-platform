# fp-merge-b: batch m5b @3072e78fbfbfb3f270ba989ab441dd9962e0ac88 - queue ONE GX10 run
Base: main 16fc921e (m4b landed). Not stacked.
PRs (services/ only, 4 commits, clean cherry-picks, identity Don Hagell author+committer, nothing under .github/, no secret or estate address in diff): 702 (41443a2), 691 (392392a), 405 (fc6b549, 2 commits). Source heads unchanged at build.
Evidence: reviewer PASS naming each head (702/691 ssl-ff-reviewer-3, 405 ssl-ff-reviewer-3 + lane15) and a GX10 16/16 report naming each head (702 verifier-4, 691 verifier-1, 405 verifier-6). Old reports (2026-11-04/05): batch run is the freshness check.
Needs: CI 7/7 on the batch PR and GX10 16/16 naming the head. Verifier item: RUN:BRANCH batch/2026-11-08-m5b@3072e78.
Left out: 689 660 489 (conflict on cherry-pick, B-REBUILD), 862 (GX10 FAIL), 808 (15/16), 597 584 (tools FAIL), 907 704 934 890 876 545 535 524 511 492 (PASS WITH CONDITIONS not shown met), 592 563 (standing merge condition), 594 (stale run), 419 411 (BLOCK as duplicate/lineage), 694 (superseded by 890).
