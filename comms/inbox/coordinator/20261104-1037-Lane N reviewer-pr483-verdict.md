# Reviewer (lane B, claude-approver): PR 483 (C-1203, DRAFT) tests for `claude_approver.client.make_client`

**Verdict: PASS WITH CONDITIONS on head `62b4d6534127d33c76ac6d28e003941ea8a73836`.** HIGH CARE (API key handling). The PR is a DRAFT; the verdict is on this exact head. Head unchanged at start and end; base cd3b7690 (main is not contained, tests only, one new file); 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Source under test (HIGH, read): `claude_approver/client.py:20-28` `make_client(key)`: imports `anthropic` inside the function and returns `anthropic.Anthropic(api_key=key)`; the module docstring says the key is never logged, echoed or put in an exception message. New `tests/test_client_c1203.py` (+91, 6 tests).

## Objections first
1. The test environment has no `anthropic` package, so "importing the module does not import the SDK" is checked against a sys.modules fake and the real absence; a guarded top-level `try: import anthropic` is invisible there (survivor below).
2. The claim "never put in an exception message" is tested only against the complete key, so a message that leaks a prefix of the key passes (survivor below). With a credential this is the pin that matters most.
3. A draft PR can still move; I reviewed the head named above and nothing later.

## Measured (GX10 ~/ff-work/wt-ln483, relative PYTHONPATH, own venv, python -B)
New file 6 passed. CI at read: see Conditions. 16-suite not run by me.

## Mutants (26 rows on client.py; source restored, worktree clean)
| Behaviour pinned | Killed | Survived |
|---|---|---|
| I1 importing the module does not import the SDK | 3 | 1 (gap: a module-level `try: import anthropic` guarded by `except ImportError` passes in an SDK-less environment) |
| K1 only `api_key=<key>` is passed | 5 | 1 (gap: `key.strip()`; no test key has whitespace) |
| U1 the SDK instance is returned unwrapped | 3 | 1 (neutral: an attribute added to the same instance keeps identity) |
| N1 a new client per call | 2 | 2 (both INVALID: my edits left an unused cache and an unused import) |
| E1 an SDK error reaches the caller unchanged | 4 | 0 |
| M1 a missing SDK is an ImportError that does not carry the key | 3 | 1 (**gap**: an ImportError that carries the first 4 characters of the key passes) |
Totals counted from the table: killed 3+5+3+2+4+3 = 20; survived 1+1+1+2+0+1 = 6; 26 rows. Of the 6 survivors, 2 are my invalid mutants, 1 is neutral and 3 are real gaps. N1 has only 2 kills because 2 of its 4 mutants were no-ops; a re-run would be needed to count a third and fourth real kill (not done).

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (a draft may need CI asked for).
- C2: GX10 16-suite 16/16 on a head containing main (the PR body says not run).

## Findings (non-blocking; new PR only)
- F-483-1 MEDIUM-LOW: pin that the ImportError text holds no part of the key (a 4-character prefix leak passes today).
- F-483-2 LOW: a key with surrounding whitespace is passed as given (K1), and an SDK-less import of the module with a guarded top-level import is caught by checking the module source or `sys.modules` after import with the SDK PRESENT (I1).
