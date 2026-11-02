# Lane 1 report: Q-91 follow-up on PR 445 (draft PR 449)
Reviewer Q-91 (Lane 7) passed PR 445 head 307b1cf0 with conditions (CI and GX10 on that head). No push to 445: head frozen, it is unchanged. The LOW findings are in draft PR 449, branch lint/auth-headers-q91-followup, head ece150d7, stacked on 445's branch (base = that branch). First push; resets reviewer and verifier gates for 449 only.
- F1: operator_headers() is a finding too; two sites allowlisted (field-agent canary.py, ops-console api.py). Allowlist 35 keys, 42 uses.
- F2, F5a, F5c: pins (every tracked top-level directory with Python is a scan root; bare star import; alias multiplicity). F5b: a duplicate allowlist key is refused. F3, F4, F6: docstring.
- Red first: commit efc38180 (5 red: four operator_headers shapes, duplicate key), commit ece150d7 implements. Real mutant (operator_headers call in a spend-governor cli file) turns the repo test red; restored.
- Tests: the file 35 passed (Windows). Not run: 16-suite set; GX10 on ece150d7. Tests only.
- Not done (Q-91 F7 and C-1150 F2): migrating the 40 sites to the guarded auth; no card exists; needs field-core GuardedOperatorAuth wiring per service group (design 4.4).
- Merge note: if 449 lands, it goes after 445 (it contains 445's two commits).
