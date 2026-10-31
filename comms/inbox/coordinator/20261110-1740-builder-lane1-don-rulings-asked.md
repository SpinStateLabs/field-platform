# Builder Lane 1: Don's answers to the open decisions I asked (2026-10-31, in the session)

Don said "ask me about decisions"; I asked eight, all answered with my recommendation:
1. PR 395 (C-553): contract writes stay FAIL-OPEN when the ledger is down (gap counted on /health, exception type only in the log).
2. PR 407 (C-505): open ONE FIX CARD PER SERVICE for the DEBT API-reply sites the lint allowlists (coordinator to number them; I will take them after PR 407 is reviewed).
3. PR 325: keep the removal date 2027-01-31 (floor test only).
4. C-504: leave the CLI print sites (lifecycle-manager cli.py, ops-console cli.py) printing exception text to an operator terminal.
5. PR 383: operator log-only is NOT open (no operator line in the startup warning).
6. PR 372: keep the federation BLOCK-reason relay; ADD a size cap on the SDK transport read (follow-up, I build it stacked on PR 372).
7. PR 381: the four proxy-environment clients wait for C-487 (PR 365).
8. PR 397 follow-up: ONE PUBLIC-SAFETY CARD for the remaining class items outside the C-561 rulings (names in the timekeeping skill file and manifest, mailboxes in plugin metadata files, scene4.mp4 tracked, two-letter customer codes); history stays (option c). I take it (claiming it as C-758 follow-up; coordinator may number it).
Also taking C-1059 (assigned): PRs 359 and 362 dirty against main (merge main into their branches, no force-push); PR 326 is superseded by PR 372 (head 1b8f9e3 carries the same commit plus fixes): I will not merge into 326, the coordinator should close it.
