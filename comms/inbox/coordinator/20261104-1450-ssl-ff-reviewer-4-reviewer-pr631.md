# Reviewer report: PR 631 @ 3889a7a772060409987f099469d62bf0ebd98178 (claude-approver: the agent map and tool map refuse a duplicate JSON key and NaN, fail closed, S3-9)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). One commit on origin/main b963407a (the current tip); `git merge-tree --write-tree origin/main pr631` clean. 2 files (+101/-2): claude_approver/config.py (+31/-2) and tests/test_agent_map_strict_json.py (+70). Author and committer Don Hagell 13129187+dhagell@users.noreply.github.com, trailer Sonnet 5.5 (HIGH).

## Objections first
1. Fail-closed means an operator's config with a harmless duplicate (a copy-paste artefact) now empties the WHOLE map: every governed call of the approver is then denied or untouched until the file is fixed. That is the intended direction for a policy file, and the error is visible on `/stats`, but it is an availability change for anyone with an existing duplicate in a live map; the PR does not say how many live maps carry one (I do not know).
2. The duplicate check applies to every object at every depth, including skipped keys such as `_comment` (the PR pins this); a map that uses repeated `_comment` keys as separators will now be refused.
3. The two parsers now differ from other JSON loaders in the repo only by the strict hook; the sealed-ledger witness pattern the docstring cites is the same idea (not re-read by me).

## Verified (run by me)
- Baseline on the exact head: tests/test_agent_map_strict_json.py 13 passed; whole services/claude-approver/tests 328 passed (relative PYTHONPATH, all service sources).
- Code read: `_no_duplicate_keys` raises `_DuplicateKey` (a ValueError subclass) on the second sight of a key; `_no_constants` refuses `NaN`, `Infinity` and `-Infinity`; both `parse_agent_map` and `load_tool_map` catch `_DuplicateKey` BEFORE the generic `ValueError`, return an empty map with a fixed error text, and never put the key in the text.

## Mutants (mutations of claude_approver/config.py; scratch worktree on the head; baseline 13 passed; kill = at least one failure in the PR's file)
| # | Mutant | Result | Killed |
|---|---|---|---|
| D1 | duplicate keys allowed (last wins) | 6 failed | yes |
| D2 | the internal exception message echoes the key | 13 passed | NO (equivalent, see below) |
| D3 | `object_pairs_hook` dropped | 6 failed | yes |
| D4 | duplicates allowed (hook replaced by a non-raising one) | 6 failed | yes |
| N1 | NaN/Infinity allowed | 4 failed | yes |
| N2 | only NaN refused | 2 failed | yes |
| A1 | agent map: duplicate reported as "not valid JSON" | 5 failed | yes |
| A2 | agent map: duplicate keeps an entry (map not emptied) | 4 failed | yes |
| A3 | agent map: error text changed | 5 failed | yes |
| T1 | tool map: duplicate reported as "not valid JSON" | 1 failed | yes |
| T2 | tool map: plain `json.loads` | 2 failed | yes |
| T3 | tool map: duplicate branch removed | 1 failed | yes |
| S1 | agent map: plain `json.loads` | 8 failed | yes |
| S2 | `except` order swapped (ValueError first) | 5 failed | yes |
Totals counted from the table: 14 mutants, 13 killed, 1 survived (D2). D2 against the whole claude-approver suite: 328 passed, baseline 328: it survives everything, and it is equivalent: the `_DuplicateKey` message is caught and replaced by a fixed text before it can reach any output, so the "never echoes the key" test (which checks `m.error`) cannot see it. The comment in the code ("never the key itself") is true of the output, not enforced for the internal message; harmless today, one future `str(exc)` away from a leak (LOW).

## Findings
- F-S39-1 LOW: D2, if anyone later surfaces the exception text, the key would leak; drop the f-string temptation by keeping the fixed text, or test the exception text.
- F-S39-2 LOW: objection 1, no inventory of live maps with duplicates; the first deploy after this PR needs a one-line check of the live maps (Don's step, not mine).

## Verdict: PASS on 3889a7a772060409987f099469d62bf0ebd98178
Head frozen; LOWs go in a NEW PR. CI green and the full GX10 run on this exact head per the coordinator procedure. Not run by me: CI, GX10, any live map.
