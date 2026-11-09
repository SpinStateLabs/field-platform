# fp-builder-d: identity-leak rebuild

Nine of my PRs had commits authored as the string donhagell@gmail.com with an empty email. Rebuilt each on a new branch from current origin/main (cherry-pick -n + commit -C --reset-author, identity env vars on every command), patch-id identical to the old patch, authors verified as Don Hagell <13129187+dhagell@users.noreply.github.com> on remote. Old branches/PRs untouched, none closed, no force-push.

| old PR | card | new draft PR |
|---|---|---|
| 999 | S12-1 | 1018 |
| 1001 | S12-4 | 1019 |
| 1003 | S12-6 | 1020 |
| 1005 | S12-7 | 1021 |
| 1006 | S12-8 | 1022 |
| 1007 | S12-10 | 1023 |
| 1009 | S12-11 | 1024 |
| 1010 | S12-13 | 1025 |
| 1014 | S12-14 | 1026 |

Not covered: closed PR 1002 (S12-5, duplicate of 850) still has branch fb-d/s12-5 with the bad author on origin; delete that branch if the coordinator wants it gone. Old branches fb-d/s12-{1,4,6,7,8,10,11,13,14} still carry the address. Tests not rerun (patch identical). Decision comments from Don are on the old PRs 1005/1009/1010.
