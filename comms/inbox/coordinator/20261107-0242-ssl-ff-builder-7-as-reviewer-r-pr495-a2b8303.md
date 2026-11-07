# Delta review PR 495 (force-gateway: junk hygiene/budget env settings fall back to defaults; scout S-B2) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS** on head `a2b8303fbf248ecdcb3e77e057f55ad752a0dd2c` (4 code-relevant files: api.py, one test file, docs/ENVIRONMENT.md). Reviewer-8's C1 (rebase; ENVIRONMENT.md conflict) and C2 (finite values that switch the detector off) are CLOSED, measured below. Two items are Don's decisions, not defects. Standing gate: CI and GX10 on this head.

Independence: I did not build or fix this PR (6 commits, none mine; builder-6 pushed the condition fix per its note).

## Decisions for Don (not blocking)
1. The ceilings are the builder's picks, not a ruling: band < 1, window 1..1000, baseline windows 1..100, latency budget > 0 and <= 60000 ms, bypass cooldown 0..10000. Change the constants (api.py MAX_*, BAND_BELOW) and the ENVIRONMENT.md rows together.
2. Behaviour change vs main to know: a finite, in-range-by-the-old-rules value ABOVE a ceiling (e.g. a window of 2000, a budget of 120000 ms) used to be honoured and now falls back to the default silently ("nothing is logged", as the rows say). I cannot see any estate's settings; the defaults are unchanged.

## Checks (HIGH, run by me)
- Identity: 6 of 6 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Shape: second parent of the head is current origin/main ff06b3398 (not behind); `git merge-tree` against origin/main is clean. Diff vs main: ENVIRONMENT.md +/-22, api.py +45, test file +125 (3 files).
- Code read: `_env_int(name, default, minimum, maximum)` and `_env_float(name, default, *, maximum=None, below=None)` replace the five bare reads in create_app (api.py:832-838); ValueError, NaN, infinity, <= 0 (float), out of range all return the default; an explicit create_app argument still wins; no default changed (5, 0.15, 2, 250.0, 10).
- Docs match code: the five ENVIRONMENT.md rows (lines 115, 117, 124, 125, 128) state the same ranges as the constants; `environment_anchors.py --check`: 0 wrong anchor row(s); test_environment_doc 62 passed.
- Tests on the exact head (Windows, py3.14): `test_hygiene_env_guard_sb2.py` 69 passed (238 s: each case builds the app; the box is loaded).

## Mutants (6 on the new ceilings, one at a time, restored and tree verified clean; counted from the table)
| # | mutant (api.py) | result (killing test) |
|---|---|---|
| M1 | MAX_HYGIENE_WINDOW = 10**12 | KILLED (`..._accept_their_ceiling_and_refuse_one_more[FORCE_HYGIENE_WINDOW-...]`) |
| M2 | band bound inclusive (`value > below`) | KILLED (`test_band_must_be_below_one_...[1-0.15]`) |
| M3 | `_env_int` ignores the maximum | KILLED (`..._refuse_one_more[FORCE_HYGIENE_WINDOW-...]`) |
| M4 | bypass cooldown ceiling 10**12 | KILLED (`test_create_app_falls_back_...[cooldown-10001]`) |
| M5 | latency budget ceiling dropped | KILLED (`test_create_app_falls_back_...[budget-huge]`) |
| M6 | integer maximum exclusive (`< maximum`) | KILLED (`..._refuse_one_more[FORCE_HYGIENE_WINDOW-...]`; same test, the ceiling itself) |
Totals: 6 attempted, 6 killed, 0 survived, 0 not applied.

## LOW (optional, new PR)
- `services/force-gateway/README.md` (lines 134-150) and `.env.example` (148-152) name the five settings and defaults but not the ranges; only ENVIRONMENT.md states them.
- Silent fallback is still by design (an operator who types `0,3` gets 0.15 and is not told); reviewer-8 raised the one-line-warning convention question already.

## Not verified
CI; GX10; Linux; the full force-gateway suite on this head (I ran this PR's file and the environment-doc tests); any estate's current values for these settings.
