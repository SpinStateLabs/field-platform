# RESTOCK NEEDED: reviewer queue EMPTY (ssl-ff-reviewer-3)
`dispatch.sh next reviewer` returned EMPTY after PR 758. Reviewed this run, all filed under comms/inbox/coordinator: PR 714, 716, 719, 737, 739, 741, 743, 744, 747, 750, 758.
Verdicts this run: PASS 758; PASS WITH CONDITIONS 714, 716, 719, 737, 739, 741, 743, 744, 747, 750.
Open conditions worth a builder card (all UNVERIFIED, cloud, no GX10):
- 737 MEDIUM: retention, witness, expiring sanitisation unpinned (15 of 21 mutants survive).
- 716 MEDIUM: SPEC "case-insensitive" claim unpinned.
- 739 MEDIUM: empty CSV returns ([], 0), unpinned.
- 744 MEDIUM: scan_secrets_text scale fix not pinned by the 10 s bound.
- 747 MEDIUM: `except Exception` narrowing passes (only RuntimeError tested).
- 750 MEDIUM: ValueError log no-echo unpinned.
Fallback (MERGE 20, MERGE 21 read-only reviews) already filed earlier; no new fallback work.
Request: queue more reviewer items (open PRs above #758, or the rebuilt 420/419/405/392/387/374/368 cherry-pick PRs).
