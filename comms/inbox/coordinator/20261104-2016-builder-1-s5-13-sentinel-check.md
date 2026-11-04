S5-13 sentinel /check bounds + registry-id shape check. PR #689 (draft). 25 tests, 9 mutants killed, sentinel suite 288 pass, lints pass.
HIGH CARE policy point: only adds refusals. Decision for Don: BLOCK R.unregistered (chosen) vs 422 for a malformed agent_id; context limits 50 keys/16 KiB are my pick.
