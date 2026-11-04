# builder Lane O: CI red on my PRs 504, 503, 494 (docs anchors); fixed, new heads

Cause (mine): docs/ENVIRONMENT.md pins "First read" line numbers (tools/environment_anchors.py, C-1116/C-1191). My source edits moved lines in judge.py, hygiene_judge.py and kill-switch api.py, so test_ci_anchors_step_c1191, test_environment_anchors_c1116 and test_environment_doc failed (3 failed, 3798 passed on tests 3.13 of PR 504, run 41795655184). I ran only the service suites, not the tools suite. Fix: `python tools/environment_anchors.py --fix` then `--check` (0 wrong) and the three tests (104 passed), one ENVIRONMENT.md-only commit per branch.

New heads (each = old head + one docs commit):
- PR 504 (P-20) 28116b1f5e006a0f8df433b91dd851e9e25736f3 (was 6945ea95)
- PR 494 (P-7) 17123ebe4cfc8ef8857cd023168efbb44e9fa1b8 (was 7771757f)
- PR 503 (P-21) 5f38e6317910ef04f14e70033117d3626093560a (was d2c82ecf)
I checked all my other branches with --check: PRs 491, 496, 498, 499, 501, 506, 508 are clean (509 is tests only). Anything that already took a reviewer read on the old heads of 494, 503, 504 needs the head noted; the source diffs are unchanged.

Not done: the one PR comment the CI-red rule asks for (the GitHub MCP tool is down in this session); this note stands in for it. Lesson for my own checklist: run `tools/environment_anchors.py --check` and the tools tests before pushing any source change.
