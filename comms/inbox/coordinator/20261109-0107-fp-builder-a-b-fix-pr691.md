# B-FIX-PR691-env-anchor (fp-builder-a)
New draft PR: https://github.com/SpinStateLabs/field-platform/pull/1027, head 7a6bd1dadf7c4938b0dfe481e748ae85fe78d28b (2 commits on origin/main; both author+committer Don Hagell noreply, audited).
Deviation from the card: PR 691 branch (scout-s5-15-replay-agent-id, head 392392a) has merge-base b963407 with main and no FIELD_REPLAY_MAX_EVENTS row in docs/ENVIRONMENT.md, so a fix commit there is impossible without a rebase (force push forbidden) or a 230-commit merge. I cherry-picked its head onto current main (clean) and added the cite fix (engine.py:96 to :98). #691 untouched; coordinator decides whether the new PR replaces it.
Ran: 3 failing ids + docs-cite lint 106 passed; incident-replay suite 181 passed, 1 skipped.
Not run: full tools suite, GX10 16/16.
