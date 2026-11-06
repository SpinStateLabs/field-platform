# B-COND-PR743-9140128: LOW condition pushed on PR 743, new head 24a5c3635100

Added test_the_count_is_per_token_not_per_agent_or_per_grantor (two tokens for one agent, three grantors, store.count() == len(list()) == 4 and /health token_count 4). Mutants M6 (COUNT(DISTINCT agent_id)) and M17 (grantor filter) both now killed. 4 tests in the file pass (PYTHONUTF8=1); no source change. Identity Don Hagell both fields. Open: CI, re-review.
