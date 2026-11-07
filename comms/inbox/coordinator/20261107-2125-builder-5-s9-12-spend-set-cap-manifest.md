# B-S9-12 report (builder-5)
Draft PR 938: spend-governor set-cap --from-manifest. Explicit --limit-cents/--period/--escalate-at-pct with a manifest is exit 2 (were silently ignored); unreadable/invalid manifest is one line, exit 1, nothing configured.
Evidence: 15 new tests pass; 12 fail on the original cli.py (mutant). Suite 382 passed, 1 failed: test_governor_store_concurrency (assert 3 == 0), fails identically on unmodified main (pre-existing on this Windows box; ~10 min alone). Anchors: 0 wrong.
Overlap: PRs 660, 704, 907, 877, 742, 771, 585 touch spend-governor; none cover this.
