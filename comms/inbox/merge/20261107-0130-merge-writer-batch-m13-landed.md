# merge-writer: BATCH m13 LANDED on main (fast-forward), 8 PRs
Old main d6db693047791b56c1e3b5789f1ef033e4e58a93 -> new main ff06b3398398124e5655a0edb463ed9be9a40881 (ls-remote verified; branch batch/2026-11-07-m13). Plain fast-forward, no force.
Gates (HIGH): source heads re-verified equal at push time; CI 7/7 each; latest reviewer verdict on each head PASS with no conditions, no open B-COND card; GX10 16/16 on ff06b339 (verifier-5, 20261107-0057); origin/main ancestor; 15 commits author+committer Don Hagell noreply; nothing under .github/.
Landed PRs: 439 496 498 503 506 508 666 854 (854 = S2-4 R-1 rollback tests, reviewer-9 PASS on 2fef9a2c).
Rescan result: every other PASS head either conflicts with main at cherry-pick (352 362 399 443 453 465 478 479 481 504 552 555 628 660 686 689 747 772 779 784 789 792 803 823 824: need rebase or are already on main in another form) or is on main already (m12b). 400 472 774 await builder fixes (see m12b report).
Close step: pending per-set approval (classifier). Open and landed: the 52 PRs of m12b plus these 8.

CLOSE STEP UPDATE (2026-11-07): done. All source PRs of this batch (and old 374 where named) are closed, on Don's chat approval; the earlier "blocked/pending" wording above is superseded.
