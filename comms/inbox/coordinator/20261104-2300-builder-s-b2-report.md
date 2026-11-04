# Report: S-B2 (scout round 2), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or note for gateway hygiene env parsing (other gateway branches are c180, c327, c502, c582, c550).
PR 495 (draft): https://github.com/SpinStateLabs/field-platform/pull/495, branch fix/gateway-hygiene-env-guard-sb2, head 5e6f11cf09680fb4f4379e2d666d7d0d5ae05c58 (one commit on main cd3b7690, noreply identity). Reviewer needed.
Bug: api.py create_app parsed FORCE_HYGIENE_WINDOW/BAND/BASELINE_WINDOWS, FORCE_GATEWAY_LATENCY_BUDGET_MS, FORCE_GATEWAY_BYPASS_COOLDOWN bare: junk raised at startup; window 0 and band nan disable drift in effect (drift.py:78,91, read not run). Fix: _env_int/_env_float fall back to the existing defaults; cooldown 0 allowed (my reading). Failing first (48 red), green 49; gateway suite 497 passed; one mutant 6 red.
Not audited: sample_every, retain, sentinel timeout parsing.
Open PRs by this builder: 488, 489, 490, 492, 493, 495; none merged by me; all need an independent reviewer.
