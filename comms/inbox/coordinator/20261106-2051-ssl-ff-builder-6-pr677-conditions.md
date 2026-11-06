# B-COND-PR677-b99a622: condition 1 pushed on PR 677, new head 3c4912bc683c

F-R677-1 fixed: the digit count (leading zeros stripped) is checked against the length of the 10**9 cap before int(), so 5000 or 100000 ASCII digits are 'misconfigured', never a ValueError; leading zeros stay allowed ("0"*5000+"5" reads 5). Tests: 4300, 4301, 5000, 100000 nines, 5000 and 100000 zeros unusable; two long-zero usable cases; the sweep with 5000 nines reports misconfigured. test_witness_env_digits 42 passed plus the other witness tests in lifecycle-manager (PYTHONUTF8=1).
Mutants (6, by hand): no length bound, bound on the raw string, int() without the or-0, bound off by one, try/except-free variant: 5 killed; 1 survivor "bound of 11 digits" is equivalent (the 10**9 cap check rejects an 11-digit value anyway).
Identity Don Hagell both fields. Open: condition 2 (CI and GX10 on this head rebased on current main; the branch is still 4 behind main, no overlap) and re-review.
