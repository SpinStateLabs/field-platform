# Lane O reviewer: PR 495 (S-B2, force-gateway hygiene, latency-budget and bypass-cooldown settings fall back instead of crashing or disabling drift) @95e29cf696f68f95bcf54494a1f93f2f3ddea10b. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 95e29cf6. Lane A (force-gateway). Two commits on main cd3b7690 (code 5e6f11cf, then a docs anchor re-anchor 95e29cf6; the builder's report names only 5e6f11cf, the head moved), contains main: yes; all Don Hagell noreply as author and committer (HIGH). I did not write the head. Claimed through dispatch.sh (R-PR495-5e6f11c).

Objections first: (1) silent fallback: a typo in FORCE_HYGIENE_BAND, _WINDOW, _BASELINE_WINDOWS, FORCE_GATEWAY_LATENCY_BUDGET_MS or _BYPASS_COOLDOWN now runs with the default and says nothing (no log line in _env_int/_env_float), where it used to refuse to start; an operator who set 0.9 and mistyped "0,9" gets 0.15 without knowing. The sibling resolve_telemetry_window has the same silent shape, so this is consistent but still hides a misconfiguration (MEDIUM-LOW, design call for Don). (2) DOCS NOW WRONG (F-O495-1 MEDIUM-LOW, read, HIGH): the docs commit only moves the anchors. docs/ENVIRONMENT.md rows FORCE_HYGIENE_WINDOW, _BAND, _BASELINE_WINDOWS, FORCE_GATEWAY_BYPASS_COOLDOWN and FORCE_GATEWAY_LATENCY_BUDGET_MS still say "non-integer raises ValueError at app start" / "non-numeric raises ValueError at app start"; after this PR they fall back to the default. `tools/environment_anchors.py --check` reports 0 wrong anchor row(s) because it checks anchors, not the behaviour text. (3) "cooldown 0 allowed" is the builder's reading (0 = no bypass window); I did not confirm what the bypass code does with 0 (I do not know).

Run here (cloud, relative PYTHONPATH of every service src and packages src): new file 49 passed; whole force-gateway suite 497 passed, matching the builder. NOT run: the 16-suite set, CI.

Mutants on api.py (28 written, 1 did not apply and is excluded; 27 run, scratch worktree on the exact head; each against the PR file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants run | Killed | Survived |
|---|---|---|---|
| B1 window junk falls back to 5, minimum 1 | 4 | 3 | 1 |
| B2 band junk falls back to 0.15 (positive finite) | 4 | 4 | 0 |
| B3 baseline windows junk falls back to 2 | 4 | 4 | 0 |
| B4 latency budget junk falls back to 250 | 4 | 4 | 0 |
| B5 cooldown minimum 0, junk falls back to 10 | 4 | 4 | 0 |
| B6 good values honoured | 4 | 3 | 1 |
| B7 explicit arguments win over the environment | 3 | 2 (1 by older tests) | 1 |
| Total (counted from the rows) | 27 | 24 | 3 |
B7 has 3 runnable mutants (the fourth did not apply), under the 4 asked.

Survivors (3, all LOW real pin gaps):
- F-O495-2: FORCE_HYGIENE_WINDOW minimum 2 instead of 1 survives: the value 1 itself is never tested (only 0, -3, 2.5).
- F-O495-3: an integer setting of 50 or more is never tested (all good values are small), so a cap on valid integers would survive.
- F-O495-4: an explicit latency_budget_ms of 0.0 treated as "unset" survives; the explicit-argument test uses 5.0 only (the cooldown twin is killed by an older test).

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 F-O495-1: correct the five ENVIRONMENT.md behaviour cells in this PR (they now state a crash that no longer happens), or name it as a follow-up card.
Optional, NEW PR only after the head is frozen: a warning log line on fallback (objection 1, Don's call); F-O495-2/3/4 pins.

Tokens/cost line: not available to me. I do not know.
