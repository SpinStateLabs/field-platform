# builder-5: B-REBUILD-PR408 -> draft PR 557
- Rebuilt #408 (old head 45a9bee) on origin/main 97dcfec: https://github.com/SpinStateLabs/field-platform/pull/557. Old PR untouched.
- Range-diff: commits 4-8 identical; commits 1-3 differ only by conflict resolution (main's C-1130 already tokenised mailboxes to contact-N@example.com; kept the PR's client placeholders + main's mailbox token; invoicing block took the PR's fully-placeholdered text). HIGH.
- Test: tools/tests/test_skill_public_safety_c1088.py 24 passed, 1 skipped (local).
- MY ERROR: first push (branch rebuild/pr408-public-safety) had 2 commits with committer "dhagell <>" (cherry-pick --continue lost env identity; I checked only HEAD). Pushed before noticing. Re-authored on rebuild/pr408-public-safety-v2 (tree identical) and used that for the PR. The first branch needs deleting by someone with authority (I may not force-push/delete). Lesson: check identity on ALL commits in origin/main..HEAD before push.
