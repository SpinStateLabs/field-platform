# builder-5: REBUILD PR 368 -> draft PR 795

PR: https://github.com/SpinStateLabs/field-platform/pull/795 (draft, 11 commits, identity checked on all). Original PR 368 untouched; it was 248 commits behind main aab217d3.
Method: cherry-picked all 11 commits oldest-first, no conflicts. range-diff: 10 identical, 1 differs only in ENVIRONMENT.md context line pins (main moved); net diff identical (27 files, +3194 -2).
Verified: field-mcp suite in D:/venvs/field-mcp-l1: 201 passed, 2 failed (test_stdio x2; WinError 10106 in a stripped-env child, Windows-only artefact, not compared to a baseline, not run on Linux/GX10); env/CI lints 104 passed. Mutation script not re-run (~10 min each here).
Branch: rebuild/pr368-field-mcp-tier1.
