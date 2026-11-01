VERDICT: PASS WITH CONDITIONS on 0c7a2c36d607a326e35d12ad12d85d8d3918ea18 (PR 414, Q-66; reviewer Lane 17, local; independent cross-check of Lane 7's 20261101-1345-reviewer-q66.md, which I read only AFTER finishing my own runs; I agree with it on every point I measured; the head did not move while I worked)

OBJECTIONS FIRST
1. F-Q66-1 (Lane 7's) is confirmed by my own measurement: on this head, adding an unused `import os` or `import json` to packages/field-core/src/field_core/alerts.py leaves `tools/vulture_gate.py` at exit 0 ("clean"), while an unused import of a name used nowhere else (`import colorsys`) gives exit 1 ("alerts.py:628: unused import 'colorsys'", FAILED). Vulture decides use by name across the scanned set, so the headline "a NEW unused import turns the step red" holds only for names unused tree-wide. MEDIUM-LOW (overclaim in the gate docstring and the ci.yml comment, not a code fault).
2. No GX10 run exists on this exact head (verifier B's run is on 38bc0f6e and was red on a missing vulture package; this head adds more tests that need vulture).
3. Double claim: the groomer's note 20261101-0905 is right that Lane 7 and I both took Q-66; this report is the cross-check, not a second full review.

ASSUMPTIONS
A1 Worktree detached at 0c7a2c36, own venv (3.14), vulture 2.16 (the version pinned in integration/ci-constraints.txt) installed into a scratch directory only, CI=true as the runner sets it. A2 Mutants in 14 full copies of the tree with a no-change control. A3 Public repo, scratch names only.

REASONING
1. Workflow read: ci.yml keeps a top-level `permissions: contents: read`, triggers `push: [main]` and `pull_request` only (no `pull_request_target`); vulture is installed by the workflow itself in the same step as the other pinned installs (`pip install $C fastapi uvicorn httpx pytest vulture`, with `vulture==2.16` in integration/ci-constraints.txt); the gate step (`python tools/vulture_gate.py`) has no `continue-on-error` or `if:`. HIGH (read).
2. Run: tools/tests/test_vulture_gate_b11.py 23 passed (7 min; each case runs vulture over the shipped tree); the gate on the tree itself: "clean (9 framework-signature entries allowed)", exit 0. HIGH (run).
3. Delta over Q-43's head 38bc0f6e: four commits (F-Q43-1..4): comment and docstring now say what 80% confidence reports (unused functions are NOT reported), main()'s exit codes and the vulture-did-not-run branch are pinned, the gate step cannot be skipped or made advisory, and `# noqa` and the unscanned trees (tools/, plugins/, integration/, tests) are documented and pinned. HIGH (diff read, tests run).
4. Mutants, 14 on tools/vulture_gate.py (13 real plus the control): the control (no change) SURVIVES as it must (23 passed). 11 of 13 KILLED: confidence 80 to 100; findings exit 3 treated as failure; vulture failure ignored; allow-all (`> 0` to `>= 0`); stale entries not reported; findings return 0; allowlist decrement removed; services tree not scanned; `--min-confidence` omitted; one allowlist entry removed; findings print dropped. One did not apply (no-source-dirs return) on my first try and was KILLED when I re-ran it with the right text. ONE SURVIVES: `Counter(allowlist)` to `Counter(set(allowlist))` (duplicate allowlist entries collapse): equivalent today (the nine entries are distinct) and LOW; a test that a duplicated entry covers two findings, not one, would pin the "one entry covers ONE finding" rule the docstring states. HIGH (run).
5. CI on this head, read from GitHub: tests (3.11, 3.12, 3.13, 3.14), compose-smoke, fly-image-smoke, compose-upgrade-smoke all SUCCESS; mergeable. `git merge-tree` against main (b152e955 at my check) is clean. HIGH (read).
6. Public repo: nothing but scratch names in my probes; the PR holds no estate value. HIGH.

FINDINGS
F-Q66-1 MEDIUM-LOW (confirmed, Lane 7's): overclaim "fails on a NEW unused import"; say "an unused name not used anywhere else in the scanned trees" or add a per-file check. F-L17-414-1 LOW: duplicate allowlist entries untested (survivor above).

CONDITIONS
C1 (blocking for merge per PROTOCOL): the GX10 full run on this exact head with vulture installed in its test venv (same constraints file), the same fix verifier B asked for. C2: reword the claim for F-Q66-1 before merge, or accept it as a stated limit. Not verified by me: GX10, other Python versions locally.

CONCLUSION
The four Q-43 findings are closed and the gate is strongly pinned (11 of 12 effective mutants dead, the survivor equivalent today), the workflow installs vulture itself and holds the safe trigger and permissions shape, CI is green. The one real gap is Lane 7's: the gate does not catch an unused import whose name is used elsewhere, which my measurement confirms. PASS WITH CONDITIONS on 0c7a2c36, agreeing with Lane 7.
