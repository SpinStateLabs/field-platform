# Reviewer report: PR 631 @2820e617 (claude-approver: agent map and tool map refuse a duplicate JSON key and NaN, fail closed, S3-9)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator) with the service `tests` directory for the shared fakes. Head 2820e617 sits on main b963407a (which is also the PR base): no rebase is needed.

## Verdict: PASS WITH CONDITIONS (head 2820e617d101296813f625e9f88c66074e9cfbed)
Conditions: C1 GX10 16/16 on the exact head; C2 CI green. No code defect found; 14 of 14 non-equivalent mutants killed. Nothing else blocks.

## Objections first
1. Availability: a duplicate key anywhere in the agent map (even a repeated `_comment`, pinned by the test) now empties the WHOLE map, so every governed agent's approval is refused until the file is fixed; the error shows on `/stats` (`agent map has a duplicate key`). That is the existing fail-closed rule for structural garbage, applied to a mistake that is easy to make while hand-editing (HIGH, read; test `comment-key`). Accepted by the design; the operator-facing runbook should name the new error text (not checked).
2. The text of an offending key is never surfaced (the exception message is fixed and the handler returns a fixed error); a mutant that put the key into the exception text survives because that text is never used (D4, equivalent) (HIGH, run).
3. The checks cover the two JSON inputs the PR names (the agent map in both inline and file form, and the tool map); any other JSON read in this service (for example a cursor or state file) is untouched; I did not enumerate them (MEDIUM).
4. Big or odd JSON that is valid and non-duplicate (very deep nesting, huge ints) is unchanged behaviour: `RecursionError` on pathological depth is not new, and is caught by `except (ValueError, TypeError)` only for ValueError; a `RecursionError` would escape (MEDIUM, reasoned from the handler; not run).
5. The sealed-ledger witness pattern the docstring cites is the model; the two hooks are local copies, not an import (LOW).

## Scope and identity
3 files: services/claude-approver/src/claude_approver/config.py (+31/-2), tests/test_agent_map_strict_json.py (new, 70), docs/ENVIRONMENT.md (anchor rows). 2 commits; author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH).

## Runs
Baseline (unmutated head): the new test file 13 passed; full claude-approver suite 328 passed. Mutants edit config.py one at a time; kill = the new file fails; for the survivor I ran the full suite; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| D1 | duplicate refused | duplicate check removed | KILLED |
| D2 | duplicate refused | identical-value duplicate allowed | KILLED |
| D3 | duplicate refused | strict hook not passed to json.loads | KILLED |
| D4 | duplicate refused | key put into the exception text | SURVIVED, EQUIVALENT (the text is never surfaced) |
| D5 | agent map | duplicate falls to the generic error | KILLED |
| D6 | agent map | duplicate error text changed | KILLED |
| D7 | agent map | a duplicate leaves an entry (map not empty) | KILLED |
| D8 | tool map | duplicate falls to the generic error | KILLED |
| D9 | tool map | duplicate error text changed | KILLED |
| D10 | tool map | parsed with plain json.loads | KILLED |
| D11 | agent map | parsed with plain json.loads | KILLED |
| C1 | constants | NaN, Infinity accepted as 0.0 | KILLED |
| C2 | constants | no parse_constant refusal | KILLED |
| C3 | constants | only NaN refused | KILLED |
| C4 | constants | -Infinity accepted | KILLED |

(C5, the generic error text, did not apply: the string occurs twice with a different leading text; not counted.)

Counted from the table: 15 rows (D1 to D11 = 11, C1 to C4 = 4). KILLED 14, SURVIVED 1 (D4, equivalent). Kill rate on non-equivalent rows 14 of 14 = 100%. By area: duplicate-refusal core D1 to D4 3/3 non-equivalent, agent map D5 to D7 and D11 4/4, tool map D8 to D10 3/3, constants C1 to C4 4/4.

## Findings
- F1 LOW: objection 4, a `RecursionError` from a pathologically deep map would not take the fail-closed branch; add a depth case or catch it (new PR).
- F2 LOW: objection 1, the runbook text for the new `/stats` error (not checked).

## Not verified
CI; GX10; other JSON inputs of the service; the behaviour on a pathologically deep file (F1).
