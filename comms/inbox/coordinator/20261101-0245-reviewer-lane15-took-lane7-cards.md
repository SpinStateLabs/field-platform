reviewer Lane 15 took Lane 7's seven OPEN cards on Don's instruction (C-1047, C-1048, C-1049, C-1051, C-1054, C-1056, C-1057). All seven already had a verdict report, so I checked each against the CURRENT head and closed the card with a pointer; nothing was re-reviewed from scratch.

Heads read through git at 02:40 UTC; main is still acaf5f24.
- C-1054 (PRs 400 to 403), C-1056 (331, 333, 342, 348) and C-1057 (356, 369, 375, 380, 381): the report's head equals the current head for every PR.
- C-1047 (PR 356), C-1048 (PR 375): their own reports are on older heads (3361e01, 178af63); C-1057 covers the current heads (3713e142, b5e74e24).
- C-1049 (PR 387): own report on 65a37a0; the current head 98de2c77 is covered by Lane 14's C-1055 report.
- C-1051: report on main acaf5f24; main unchanged.

One independent re-run: Lane 7's FAIL on PR 400 (F-C1054-1). On main acaf5f24, four volume driver_opts cases are refused by tools/compose_resolved_check.py check_model; on PR 400 head fe2eed3d the three cases the report names pass (type tmpfs with a forbidden device, with and without o bind; type none, o bind, device "tmpfs"), the case with a forbidden directory stays refused, and the legitimate tmpfs/tmpfs/size case passes (the intent of the change, which main refuses). Reproduced, HIGH. Docker's real handling of o=bind was not run (no docker): MEDIUM.

The verdict stands: PR 400 FAIL until F-C1054-1 is fixed and pinned. UNVERIFIED (no GX10, no CI logs).
