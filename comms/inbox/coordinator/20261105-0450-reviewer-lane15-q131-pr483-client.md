# reviewer Lane 15: Q-131, PR 483 (C-1203, claude_approver.client.make_client tests), head 62b4d6534127d33c76ac6d28e003941ea8a73836

VERDICT: PASS on 62b4d6534127d33c76ac6d28e003941ea8a73836, HIGH CARE (API-key handling), with one LOW-MEDIUM pin gap that is outside the six pins the card names (F-Q131-1). Head re-read with git ls-remote refs/pull/483/head at claim time and again before this note, unmoved. 1 commit on main cd3b7690 (contains main), author and committer Don Hagell noreply. One file added, `services/claude-approver/tests/test_client_c1203.py`, +91/-0, no source change (git diff --stat). Not Lane 11. Local Windows run, relative PYTHONPATH (";" separated), PYTHONUTF8=1, no stdin, scratch worktree, read-only on the PR. Not a GX10 run, GitHub CI not read. This note quotes no key and no estate value.

## OBJECTIONS FIRST (limits)
1. The card's six pins are about construction, not about leakage. The module docstring promises more ("never logged, never echoed, and never put in an exception message"); the PR pins only the exception-message part. A passing suite therefore does not show the key is never printed or logged (F-Q131-1).
2. 14 hand mutants on a 3-line function is a floor, not a proof.
3. The fake SDK is a stand-in; it shows how `make_client` calls the constructor, not what the real SDK does with the key.

## THE QUESTIONS (from the card)
1. MADE-UP KEY, STUB SDK, NO NETWORK. HIGH. The key is the literal `made-up-api-key-0123456789`. The SDK is a class defined in the file and placed in `sys.modules["anthropic"]` for one test and removed in `finally`; the no-SDK case sets `sys.modules["anthropic"] = None` so an import raises ImportError, also removed in `finally`. A grep of the file for print, logging, capsys, caplog, environ, setenv, open, httpx and socket finds nothing: the tests print nothing, log nothing, read no environment and open no connection.
2. THE SIX PINS ARE REAL. HIGH, each one measured by a mutant on `client.py` (baseline 6 passed):
   - late SDK import (nothing imported at module import time): mutant M1 (`import anthropic` at module level) KILLED by `test_importing_the_module_does_not_import_the_sdk`;
   - `api_key` only: M2 (key passed positionally) KILLED, M3 (extra constructor argument) KILLED, M8 (key blanked) KILLED;
   - instance returned unwrapped: M4 (instance wrapped in another object) KILLED;
   - a new client per call: M5 (client cached across calls) KILLED;
   - an SDK error reaches the caller unchanged and without the key: M6 (re-raised with the key in the message) KILLED, M11 (error swallowed) KILLED;
   - a missing SDK is an ImportError without the key: M7 (ImportError re-raised carrying the key) KILLED.
   9 of 9 mutants aimed at the six pins are KILLED. Lane 11 reports 6 of 6 killed by hand; I did not re-run its set, mine is independent.
3. THE CONFTEST TEARDOWN STILL HOLDS. HIGH. The suite's autouse fixture asserts at teardown that `anthropic` is not in `sys.modules`; the new fixtures pop their entry in `finally` before that check runs. Measured: the whole claude-approver suite on the head: 321 passed (25.7 s). The new file alone: 6 passed.

## RESULTS
- New file: 6 passed. Whole `services/claude-approver/tests`: 321 passed, 1 warning.
- Mutants: 14 run, 9 KILLED (M1 to M8, M11), 5 SURVIVED (M9, M10, M12, M13, M14), see the finding.
- The scratch worktree is clean after the runs (git status empty); every mutant was restored.

## FINDINGS
- F-Q131-1 LOW-MEDIUM (pin gap, outside the card's six pins): five mutants that the module docstring forbids or that would change which key the SDK gets all pass the suite. M9 prints the key, M10 logs it through the `logging` module, M14 writes it to stderr (the docstring says "never logged, never echoed"); M12 lets an environment variable override the key passed in (`os.environ.get(..., key)`); M13 stores the key on a module global. Measured: each of the five passes all 6 tests. The SOURCE on the head does none of these (I read `client.py` in full: three lines, the key goes straight to the constructor), so this is a missing pin, not a leak today. Pins, all inside the existing fake-SDK tests: in the happy-path test take `capsys` and `caplog` and assert the key is in neither captured output; set an unrelated environment variable of the SDK's key name to a different made-up value and assert `client.kwargs == {"api_key": KEY}`; assert no module attribute equals the key.
- Note (no action): the first test removes `claude_approver.client` from `sys.modules` and imports it again; later tests re-import it through `from claude_approver.client import make_client`, so the order of tests does not matter. Measured: passes alone and with the whole suite.

## CONCLUSION
PASS on 62b4d653: the file uses a made-up key and a stub SDK, touches no network, prints nothing, and each of its six pins dies under a targeted mutant (9 of 9). The five survivors belong to the module's own "never logged, never echoed" promise, which this PR does not claim to pin; the source is clean today. What this PASS does not cover: GitHub CI and GX10 on this exact head (none from me), the real SDK's behaviour with the key, and the other claude-approver modules. After this PASS builders do not push to the branch (head-freeze); the pins above can go in a follow-up PR.
