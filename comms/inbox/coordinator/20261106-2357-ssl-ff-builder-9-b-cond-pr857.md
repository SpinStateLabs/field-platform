# ssl-ff-builder-9: B-COND-PR857-eb08bb6 -> pushed to PR 857

PR 857 new head 3af8d248d6dfd9a03bd4b8e586b4561fd1273dc1 (one commit on eb08bb6; author AND committer Don Hagell noreply; remote head verified).
C1: docs/ROLE-AGENTS-TEAM-ACCESS.md line 3 no longer says "provisioned on the GB10 estate"; it says the manifests are drafts, a default run excludes them, and gives the `--only <FIELD id>` command.
C2: documented, not bumped (the lifetime is Don's call): the doc states expiry 2026-12-06, that a mint outliving it is refused, to set FIELD_TOKEN_TTL_DAYS below the days remaining, and to edit the manifest expiry before that date.
C3: -EnvironmentId now has ValidatePattern on the parameter; checked by running the script with 'a/b' (refused at binding, nothing read or written). The old in-block check stays.
Not run: the provisioning against an estate; CI on the new head not read. Observations (.prev overwritten on second -Replace; PROVISIONAL kill-switch endpoint) left as the reviewer listed them; Don's decisions unchanged.
