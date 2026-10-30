To: COORDINATOR. From: coordinator-assistant.

Batch BY (PR 376) merged, so main moved 63e91b2 to 5777030. Batch BZ (PR 386, based on 63e91b2) is no longer a fast-forward. Its GX10 run was clean (16 suites, 0 failed) and its CI was 7/7, but both are for the old base.

I rebuilt the same three sources on the new main as batch CA: PR 390 (draft), PR 290 (C-447), PR 319 (C-593), PR 328 (C-585), patch-ids equal to the sources. GX10 run `ca` started. Ready packet follows when GX10 is clean and CI is 7/7 on the exact head.

For you: PR 386 is superseded; closing it is yours (I do not close PRs). Source PRs 290, 319, 328 heads unchanged since their verdicts.

Generated with Claude Code
