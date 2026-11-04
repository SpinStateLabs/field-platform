# Lane O reviewer: PR 422 (F-CW-10, C-1082: compliance-crosswalk clearing a stale flag names a plain human) @2fb120e4bfd8ce86731fc087775e7cdbbad8c641. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 2fb120e4. Lane B (crosswalk). Two commits (e50c34e1 tests, 2fb120e4 the change), both Don Hagell noreply as author and committer (git log, HIGH). The head does NOT contain current main: 212 commits behind origin/main 97dcfec1 (git rev-list --count pr422..origin/main). The merge result is printed by `git merge-tree` below this line in my command output (a tree id means clean, "CONFLICT" means not); I did not rely on it for the verdict. Source: staleness.py +23/-4 (a new `_plain_reviewer_name`), a +82-line test file. I did not write the head. Claimed through dispatch.sh (R-PR422-2fb120e).

Objections first: (1) the PR text says "the same rule as check-file --fetched-by" (regwatch._named_human); the new function drops regwatch's `_CONTROL_CHARS` regex check, which I verified is a subset of Unicode category Cc (`[\x00-\x1f\x7f]`), so the rules agree (read, HIGH): equivalent, but there are now TWO copies of one rule that can drift (regwatch.py:577-585 and staleness.py `_plain_reviewer_name`). (2) a flag is cleared by a NAME the caller types: the rule proves the name is printable, not that it names a real person or that the person is the caller; "no anonymous clears" is a text rule only (read, HIGH). (3) contrast with PR 511 (agent-registry blank fields, my report 20261104-1007): that PR's `str.strip()` accepts a zero width space or byte order mark; this one refuses them through category Cf, so the two human-name rules in the repo now disagree (read, HIGH).

Run here (cloud, scratch worktree on 2fb120e4, relative PYTHONPATH of every service src and packages src plus the tests directory): new file 39 passed; whole compliance-crosswalk suite 393 passed, 5 skipped. NOT run: the 16-suite set, CI.

Mutants on staleness.py (26 written; 1 did not apply and is excluded; 25 run in a scratch worktree; each against the new test file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 a blank or non-text name is refused, never stringified | 5 | 5 | 0 |
| B2 control, invisible format and line break characters are refused | 6 | 6 | 0 |
| B3 a name with no letter or digit is refused | 4 | 3 | 1 |
| B4 the refusal messages never echo the name (one more did not apply) | 3 | 2 | 1 |
| B5 a plain name passes and is returned stripped, unchanged in case | 4 | 4 | 0 |
| B6 `clear` applies the rule before touching state | 3 | 2 | 1 |
| Total (counted from the rows) | 25 | 22 | 3 |
B4 and B6 have 3 runnable mutants each (under the 4 asked).

Survivors (3): 1 equivalent, 2 real LOW pin gaps.
- Equivalent (read, MEDIUM): moving the check inside the `with self.transaction()` block (the flag is untouched when the check raises either way).
- F-O-pr422-1 LOW: a digit-only name ("12345") is unpinned: `isalpha` instead of `isalnum` survives, although the rule says "letter or digit" (staleness.py, `any(ch.isalnum() ...)`). The tests have "R2" (a letter and a digit) only.
- F-O-pr422-2 LOW: the BLANK-name refusal can echo the original value (`{name!r}`) and the test passes: the echo test covers the plain-name and no-alphanumeric messages, not the blank one (an all-whitespace or control-only name, repr'd, would be repeated).

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head REBUILT on current main (212 commits behind; the coordinator's batch rebuild, so this is the rebuild condition; the staleness.py region may also have moved). C2 none other.
Optional, NEW PR after the head is frozen: F-O-pr422-1/2 pins; one shared name rule in field-core for regwatch, staleness and (separately) the registry (objections 1 and 3), as a design card.

Tokens/cost line: not available to me. I do not know.
