# ssl-ff-builder-9: B-COND-PR825-c6c5957 -> pushed to PR 825

PR 825 new head 9e5a572e812b07f61d53d4651016738ac9d48934 (one commit on c6c59571; author AND committer Don Hagell noreply; remote head verified).
C1 fixed by scrubbing (not by a "kept on purpose" note): `/home/spinner` -> `<gb10-home>` (22 uses), the account name `spinner` -> `<gb10-account>` (8), staged-file `c6c2c2b4cd6ccca3` -> `<sha256-prefix>`, dates 2026-10-21 / 2026-10-12 / 2026-10-03 -> `<date>`. Same line count, no line moved (environment anchors unaffected). Tests: test_deploy_docs, test_docs_no_line_cites_sd1, test_runbook_pins_c465 45 passed.
Decision for Don if he wants the account layout kept: the reviewer found it unclear whether a GB10 account layout is a "home path" under the C-606 ruling; I read it as yes. Reverting is one find-replace.
Optional LOWs not done: the `<build-id>` line about FIELD_OPERATOR_REQUIRE (could say "any image from before PR #32"), the api.py:372-400 cite off by two lines, row T4 hash prefix `3a068358`. CI on the new head not read.
