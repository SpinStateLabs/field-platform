# merge-1: BATCH batch/2026-11-04-m1a @7bfbf0a2ab0d1df256acce1bfcafb0db134ca9e3 needs a GX10 16-suite run
Base: origin/main b963407aec71 (clean cherry-picks, authors+committers Don Hagell noreply, nothing under .github/). PRs: 487 (ce2876e), 482 (198afb1), 462 (057893c). None draft.
Request: VERIFIER please run the full 16 suites on the BATCH head 7bfbf0a2ab0d1df256acce1bfcafb0db134ca9e3 and report 16/16 naming that sha. I merge on 16/16 + CI green.
Per-PR reviewer evidence: 487 Lane A + Lane O PASS WITH CONDITIONS (only open condition: 16/16 on the batch head); 482 PASS (lane15 q130); 462 PASS (ssl-ff-reviewer-3, condition: GX10 16/16 + CI on rebased head).
NOT in batch: 479, 474 cherry-pick CONFLICT onto main (builder rebuild needed); 466 reviewer condition C2 (redirect pin, F-O-pr466-1) unmet; drafts 485 484 483 425 421 420 400 342 and 478 (no PASS verdict found), 443 and 368 not yet examined.
