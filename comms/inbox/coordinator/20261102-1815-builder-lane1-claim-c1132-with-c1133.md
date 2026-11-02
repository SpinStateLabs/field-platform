# Builder Lane 1: claims C-1132 as well as C-1133 (they cannot land apart)

Finding (counts only, read from main 05942b98): the estate account's home path is the ONE absolute root the compose bind rule allows (tools/compose_bind_rules.py ALLOWED_ABSOLUTE_ROOTS), the tests in C-1133 pin that exact string, and the compose file, .env.example, ci.yml and the runbooks in C-1132 carry the same string. If C-1133 changes the rule and tests alone, the compose lint reads the real compose file and goes red; if C-1132 changes the compose file alone, the rule rejects it. So one PR must change all of them with ONE placeholder.

Plan: Lane 1 does C-1132 and C-1133 together in one draft PR, new branch from main in worktree C:\Users\donal\fpb-l1-c1133 (already made). Placeholder: the generic name "example" in the same path shape (/home/example/..., and the same for the Windows-style paths). Both estate account names in code, tests, docs and config become that placeholder; benign one-character names stay. Each pinned test is shown to still fail when the allowed root is mutated.

Deploy note for the coordinator and Don (not a change of mine to make): the compose file's default path becomes the placeholder, so the estate operators file must set FIELD_CALLER_KEYS_DIR to the real path off-repo (the same rule as F-C1048-2: Don confirms the operators file before DEPLOY, not merge). I do not know how the estate sets it today.

If the coordinator prefers two PRs or another placeholder, say so before I push; nothing is pushed yet. Public repo: no account name appears in any note, PR text or commit message.
