# Reviewer (lane B, agent-registry): PR 510 (scout S-B7) registry CLI `add` and `scan` exit 2 with a named message on bad input

**Verdict: PASS WITH CONDITIONS on head `62fe8e3144f86051fe4bd38ff6c5f7bf446719e3`.** Head unchanged at start and end; base current main; 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): `agent_registry/cli.py` (+27/-9): `add` builds `AgentCreate` in its own `try`, catches `pydantic.ValidationError`, prints `error: not a valid agent record (<field names>)`, exit 2, nothing written; `scan` `_text` also catches `OSError` (`cannot read <name> (<ExceptionType>)`), and a new `_n8n` helper maps `OSError` and `ValueError` to named `ScanInputError`s (exit 2). New `test_cli_bad_input_sb7.py` (14 tests).

## Objections first
1. The messages are built from exception TYPES and field NAMES, the right shape; a one-line regression to `{exc}` would put paths or messages into output, and the tests do not forbid it (survivors below).
2. `p.name` keeps only the file name, not the directory: the survivors show a regression to the full path also passes.
3. A `ValidationError` with an empty `loc` falls back to the word "input": fine.
4. A one-line `message` for the invalid n8n JSON could quote content if someone adds `{exc}`; JSONDecodeError text carries a position, not content, so the risk is the future edit.

## Measured (GX10 ~/ff-work/wt-ln510, relative PYTHONPATH incl. sibling service src, own venv, python -B)
New file 14 passed. agent-registry suite: PR 324 passed, 1 failed; main cd3b7690 310 passed, the SAME 1 failed (`test_the_header_name_is_the_one_the_kill_switch_sends`, `ModuleNotFoundError: kill_switch`, my venv). +14, no count down. CI at read: see Conditions. 16-suite not run by me.

## Mutants (28 rows on cli.py; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| A1 an invalid record is exit 2, nothing written | 4 | 1 (invalid: my edit was a comment after the raise) |
| A2 the message names field names, never the value | 3 | 2 (gaps: a message built from the error MESSAGES, and a constant `input`, both pass: no test asserts the field name appears) |
| A3 a valid slug still registers; a duplicate still exits 1 | 2 | 2 (gaps: the `DuplicateAgentError` handler can be replaced and a second exit-code edit can pass: no duplicate-agent test in the new file) |
| S1 an unreadable scan input is exit 2 naming the file | 2 | 3 (gaps: the full path, the exception text and a constant message all pass) |
| N1 an unreadable n8n file is exit 2 | 3 | 1 (gap: the exception text in the message) |
| N2 invalid n8n JSON is named, content not echoed | 1 | 3 (**gaps**: appending the first 30 characters of the file, the JSON error text and a constant name all pass) |
| N3 the scan uses the helper | 1 | 0 |
Totals counted from the table: killed 4+3+2+2+3+1+1 = 16; survived 1+2+2+3+1+3+0 = 12; 28 rows. Of the 12, 1 is my invalid mutant and 11 are unpinned message detail. The exit codes and no-traceback behaviour are pinned; the CONTENT of the messages is not (A2, S1, N1, N2 below 4 kills).

## Conditions
- C1: CI 7/7 SUCCESS on this exact head.
- C2: GX10 16-suite 16/16 on a head containing main.

## Findings (non-blocking; new PR only)
- F-510-1 MEDIUM-LOW: the PR text promises "never the rejected value" and "content not echoed", and no test asserts either for the n8n file (N2: appending file content passes). Add a made-up marker inside the bad JSON and assert it is absent.
- F-510-2 LOW: assert the field name is in the `add` message, the bare file name (not path) in the `scan` messages, and a duplicate `add` still exits 1.
