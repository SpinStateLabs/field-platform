# Lane 12: PR 368 with PR 356 now on main: the C-790 F-C775-5 coupling does not bite (measured; no push)

Main 3425e23f (batch cb3e) carries PR 356's `field_core.hosts`. C-790 F-C775-5 (and C-1083's card text) said that the day PR 356 landed, field-mcp's own refused corpus would go red because the two predicates disagreed on 12 inet_aton short forms (`http://127.1` among them). Measured against the MERGED version, not the a9be069 head C-790 read:

1. `field_core.hosts.is_internal_host(h, allow_names=False)` on main 3425e23f: `127.1`, `127.0.1`, `2130706433`, `0x7f000001`, `10.1`, `192.168.1` all False (refused); `127.0.0.1` and `localhost` True; `8.8.8.8`, `169.254.169.254` False. HIGH (run on main's file).
2. PR 368 head 37c19167 with main's field-core on the path: `field_mcp.hosts.SOURCE` reads `field_core.hosts` (the fallback is no longer the active predicate), `tests/test_config.py` 40 passed, the whole field-mcp suite 203 passed. HIGH (run). So a GX10 run of 368 rebased on current main should not fail on this point; the merge-order ruling C-790 asked for (C3) looks moot for the merged 356.
3. Stale wording that follows from this, NOT pushed (head freeze; Q-65 PWC on 37c19167; a docstring-only push would reset gates for nothing): `field_mcp/hosts.py`'s docstring (my fa58782) still says the two predicates "disagree on 12 inet_aton short forms". True of a9be069, not of main. The right time to drop that sentence, and the whole fallback (PR 368's docstring says the fallback is deleted once C-489 is on main), is the next condition push or a follow-up card; your call.

Not measured: which PR 356 commit changed the short-form behaviour (I did not diff a9be069 against main), the GX10 set, CI.
