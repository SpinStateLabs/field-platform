# builder-6: condition fix on PR 788
PR 788 (branch fix/incident-retro-verify-hostile-pack-s8-29): old head 3e13b523 -> new head f29b6fabadea36f8779177fd84621ca741410bbc (one commit on top; author+committer Don Hagell noreply). Applies reviewer-9 C1 and C2; C3 (GX10 gate) open.
C1: cli.py wraps _verify_pack in try/except RecursionError -> the same one line "error: could not read the pack: RecursionError", exit 1. Test: a pack with signer nested 16000 deep (json.loads accepts it on 3.14.2) exits 1 with that line and no RecursionError escaping.
C2: test with non-string raw (5, [1], {}, True) must not raise.
Mutants: removing the new except -> the depth test FAILS (killed); dropping the isinstance(raw,str) guard -> 4 raw tests FAIL (killed).
Ran (PYTHONUTF8=1): test_verify_malformed_pack.py 61 passed; agent-incident-retro suite 287 passed, 2 skipped, 1 failed: test_signatures::test_cap_applies_in_every_regex_entry_point (0.27 s vs 0.2 s timing limit; the same timing test the PR body named as its 1 failure; untouched by this fix).
Not done: the PR body still says a JSON-loaded pack "cannot" make canonical() raise; the coordinator or author should edit that sentence (I did not edit the PR body). Re-review requested on f29b6fab; the head is not rebased on main.
