# Reviewer: PR 497 (scout S-B8) agent-incident-retro: verify fails cleanly on a malformed pack

**Verdict: PASS WITH CONDITIONS on head `7f172e18aa304dfc11322c6fc2e79ebf9c547a23`.** Head unchanged at start and end (git ls-remote); base main cd3b7690; 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): `evidence._shape_problem` + a "pack shape" check at the top of `verify_pack` (+29), and `cli.verify` wraps the input reads in `try/except (OSError, ValueError)`, printing the exception TYPE only plus `VERIFICATION FAILED`, exit 1 (+14/-8); new `test_verify_malformed_sb8.py` (23 tests).

## Objections first
1. The claim "a malformed pack is a failed check, never a traceback" (evidence.py docstring) is wider than the shape check: probes below still crash `verify_pack` on a pack that passes `_shape_problem`.
2. The CLI catches only `OSError` and `ValueError`: a `RecursionError` from `json.loads` on a deeply nested file is neither (not run; MEDIUM).
3. Fail-closed: every residual crash exits non-zero, so none can turn a bad pack into an accepted one (HIGH, from the probes: each returned ok=False or raised).
4. The PR body names "report or source file" read failures as handled; no test supplies `--report` or `--sources`.

## Measured (GX10 ~/ff-work/wt-ln497, relative PYTHONPATH, own venv with typer, python -B)
New file 23 passed. Suite: PR 251 passed, 1 failed; main cd3b7690 228 passed, the SAME 1 failed (`test_scan_is_deterministic_across_processes`, FileNotFoundError from a subprocess, baseline). +23, no count down. CI when read: see Conditions. 16-suite not run by me.

## Probes on the PR head (own made-up packs built with the repo's builder; clean pack = 7 findings, 8 requests, verifies True)
Still CRASH after the PR (exception escapes `verify_pack`): a request `raw` that is an int (TypeError) or a list (AttributeError) [evidence.py step 6]; an `inputs` label that is a list, with `--sources` (TypeError unhashable) [step 8]; a flagged event payload `evidence_lines` of `[1]` (TypeError) or `[{}]` (KeyError) [step 8]; a `retro.run.started` payload `inputs` of `[1]` (AttributeError) or `5` (TypeError) [step 5b]. 6 probes crash. Fail cleanly (ok=False): ref sha256 int, ref input list, session_id list, label None, sha256 list, event payload string, events [1] / [None], fingerprint list, signature int, report_sha256 list, chain head list, NaN. (Deep nesting and huge int not run: my deep-nesting probe was itself a syntax error.)

## Mutants (35 rows; source restored after each, worktree clean)
| Behaviour pinned | Killed | Survived |
|---|---|---|
| B1 a non-object pack is refused | 5 | 0 |
| B2 signer and chain must be objects | 4 | 0 |
| B3 findings, inputs, events must be lists | 0 | 4 (redundant: other guards still fail the pack, same ok=False) |
| B4 inputs entries need label and sha256 | 2 | 2 (**real gap**: an entry missing a key is untested) |
| B5 a finding's requests need a ref with input, line, sha256 | 2 | 3 (**real gap**: only `findings:[1]` is tested) |
| B6 the clean pack still verifies | 3 | 1 (absent-key default: unpinned, harmless) |
| B7 CLI read failure: exit 1, type only, VERIFICATION FAILED | 4 | 2 (**real gap**: message echoing `{exc}` and dropping the FAILED line both pass) |
| B8 CLI covers report and source reads | 1 | 2 (**real gap**: no test uses --report or --sources) |
Totals counted from the table: killed 5+4+0+2+2+3+4+1 = 21; survived 0+0+4+2+3+1+2+2 = 14; 35 rows. Of the 14 survivors, 5 are redundant or equivalent (B3 x4, B6 x1) and 9 are unpinned claims.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head.
- C2: GX10 16-suite 16/16 on a head containing main (defence-shield is outside the 16 services; the coordinator decides what runs).
- C3 (condition fix, the only push allowed): either narrow the docstring and PR text to what the shape check covers, or make `verify_pack` fail cleanly for the 6 crashing probes above (for example one `except (TypeError, AttributeError, KeyError)` around the steps after the shape check, adding a failed check), with a test per crash class. The claim as written is false today.

## Findings (non-blocking; new PR only)
- F-497-1 MEDIUM-LOW: the 6 residual crashes (above); fail-closed.
- F-497-2 LOW: tests for B4, B5 (inputs/requests missing keys), B7 (type-only message, FAILED line) and B8 (--report, --sources unreadable).
- F-497-3 LOW: `RecursionError` from `json.loads` is not caught by the CLI (unrun).
