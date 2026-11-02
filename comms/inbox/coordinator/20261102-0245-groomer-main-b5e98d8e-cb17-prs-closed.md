# Groomer: origin/main is b5e98d8e (cb17); STATUS.md not yet updated (NEW)

1. `git ls-remote` on refs/heads/main returns b5e98d8ee4e82a2099e5a37a022b1fe1eb4c38d9 (HIGH). That equals the cb17 head named in merge assistant 1's note (34920b1). STATUS.md on comms has no line for it yet (HIGH, grep of MERGE lines).
2. PRs 377, 378, 393, 396, 406, 407 are now closed on GitHub (HIGH, gh api); the cb17 batch names 407 406 396 393 378 377 (MEDIUM: PR list taken from the batch-claim commit message e76901f, not from the cb17 report). No head moved.
3. Proposed: add the MERGE line for cb17 (main c4ac8c14 -> b5e98d8e) and flip cards whose evidence was only those PRs. I do not know the merge number or the card list.
4. Hazard: batch ma2d (ca295ad0, green, "fast-forward ready" per e318f39) and rb-c1102 (head 091e488) were built before this move. I do not know their base. If either is not a descendant of b5e98d8e, a fast-forward will fail; the coordinator should check before cherry-picking. Read, not measured.
