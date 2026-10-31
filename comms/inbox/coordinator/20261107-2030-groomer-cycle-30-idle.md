# Groomer cycle 30 (Lane 9): IDLE on cloud cards - main acaf5f2 (batch CA merged 2026-11-06: PRs 290, 319, 328), comms at pull; UNVERIFIED: no GX10/CI

Lane 9 has no unclaimed cloud-reviewer card (only C-18 and C-605, PR 57). Polling every 5 minutes; send a card or name a read.
Grooming this cycle: 3 builder cards DONE by main commits; 12 reviewer cards DONE from reports (C-933-939, 941-944, 975); conditions cards C-1007..C-1015 (PRs 341, 343, 348, 363, 364, 381, 382, 384, 391), older 815, 820, 930 SUPERSEDED; delta card for PR 341 @f1d4dbb. Highest card C-1016.
Note: main was re-created for batch CA (hashes changed: BZ2's f7baaab is now acaf5f24 on main); cards that cite old shas (BZ2, PRs 290/319/328 heads) now point at heads that are in main by patch-id, not by hash. The stacked compose PRs (345, 353, 370, 385) still need the rebase from my C-912 report.
Waiting on Don (not a blocker for lanes): the repository variable COMMIT_IDENTITY_ALLOW_DOMAIN for PR 346; soak items 3 and 4; D-9.
