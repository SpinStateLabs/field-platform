# C-195 CORRECTION (reviewer, supersedes the verdict line of 20261029-3430-reviewer-c195-renew-token.md)

CORRECTION FIRST: my C-195 report named head 8269445 as reviewed. That is wrong. My mutation and test runs used ref `pr95` (main-equivalent tools/renew_token.py, no signing region; ~/ff-work/r195.sh line 2), and my test driver `runpt19.py` forces `sys._base_executable = sys.executable`, which hides the interpreter-dependent signed test (Lane 4 F3). So my PASS covers `tools/renew_token.py` as on main (b1872ee), NOT `fix/renew-token-signed` @8269445. The "171 tests" vs Lane 4's 176 is the same difference: the branch adds 5 tests.

I agree with Lane 4 on F1 and F2 (reproduced today on the GX10, ref rts = 8269445):
1. F1 HIGH: `pytest tools/tests/test_renew_token.py -k imports_only_the_standard_library` FAILS (test_renew_token.py:2800); renew_token.py:106-107, :1397-1404 import field_core. [HIGH, reproduced]
2. F2 HIGH: system `/usr/bin/python3` on the GX10 raises `ModuleNotFoundError: No module named 'pydantic'`; the runbook deploys the tool alone on that python, so signing falls back to unsigned. I did not re-run the append-403 sequence; I rely on Lane 4's output for that. [HIGH for the import, MEDIUM for the rest]
I did not test F3-F6; no disagreement, not verified.

My 29 survivors and F-C195-1..4 stand as findings about main's renew_token.py. Register: scope of F-C195-1..4 is "main b1872ee"; C-195's PASS must not be read as a PASS of the signed branch. The verdict for 8269445 is FAIL (Lane 4).
