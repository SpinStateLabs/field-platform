# merge-writer: BATCH m14 LANDED on main (fast-forward), 4 PRs
Old main ff06b3398398124e5655a0edb463ed9be9a40881 -> new main ccd013d4f072aa8f9d420bff029359ffd8d617d1 (ls-remote verified; branch batch/2026-11-07-m14). Plain fast-forward, no force.
Gates (HIGH): source heads re-verified equal at push time; CI 7/7 each; latest reviewer verdict on each head PASS, no open B-COND card; GX10 16/16 on ccd013d4 (verifier-6, 20261107-0215); origin/main ancestor; 7 commits author+committer Don Hagell noreply; nothing under .github/.
Landed PRs: 665 859 861 863 (859/861/863 include the B-RT2 alerts / stage controller per-step alert fixes).
Not taken from the coordinator's list: 840, 837, 838, 841, 844, 850, 851, 857 (no PASS on current head, conditions open, or CI not green). Other PASS heads (352 362 478 504 552 555 628 651 686 803 823 824) conflict with main at cherry-pick; 399 443 453 465 479 481 660 689 772 779 784 789 792 have open rebase cards.
Close step: sources 665 859 861 863 still open; closing only on a per-set approval.
