# Reviewer report: PR 575 @ 2b1b23b3c6cf84b377dc86512877b81a0d138957 (tests only: pin 11 surviving mutants across five services)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10; the PR says the same). One commit on origin/main 97dcfec1 (main is now b963407a; `git merge-tree --write-tree origin/main pr575` clean). 6 new test files, +241 lines, no production code: attestation-reporter test_render_pdf_lane_r.py, claude-approver test_config_lane_r.py and test_usage_cursor_load_lane_r.py, delegation-authority test_mutant_survivors_lane_r.py, incident-replay test_markdown_sections_lane_r.py, kill-switch test_parse_method_lane_r.py. Author and committer Don Hagell 13129187+dhagell@users.noreply.github.com, trailer Sonnet 5.5 (HIGH).

## Objections first
1. A tests-only PR that claims to kill "11 surviving mutants" gives no list of the mutants (the commit message says 11; the files name the functions). I rebuilt mutants from each file's docstring and from reading the production functions, so my list is mine, not the author's; a surviving mutant of theirs that I did not rebuild would be invisible to this review.
2. Tests that mock `subprocess.run` and `shutil.which` (the PDF and browser tests) pin the calling shape, not a real browser; they cannot show a real Chrome renders a PDF.
3. Six files in five services is a wide blast radius for a Lane R sweep; each is small and independent, which is why I ran them together and per service.

## Verified (run by me)
- Baseline on the exact head: the six files together 26 passed (relative PYTHONPATH, all services on the path).
- Unmutated whole-service suites for the survivor check: claude-approver 325 passed, delegation-authority 259 passed, kill-switch 277 passed.

## Mutants (mutations of production code; scratch worktree on the head; kill = at least one failure in the six files)
- attestation render.py `render_pdf`: R1 no-browser branch removed; R2 its detail text changed; R3 it returns True; R4 an empty PDF counts as success; R5 a missing PDF counts as success; R6 success detail drops the browser name; R7 the command's first word is not the browser. All 7 killed.
- claude-approver config.py: A1 `field_ids` counts entries with a problem; A2 counts entries without an id; A3 problem test inverted; A4 AGENT_MAP naming a file displaces the FILE variable; A5 AGENT_MAP naming a file is never read (5 killed; A1-A3 were killed after I fixed my first pattern, which matched two lines); A6 an inline JSON string treated as a path: survived.
- claude-approver core.py `UsageCursor.load`: U1 non-object cursor accepted; U2 non-object snapshot accepted; U3 corrupt cursor leaves `error` unset (3 killed); U4 `TypeError` not caught; U5 a missing file sets an error (2 survived the PR's file).
- delegation-authority: D1 `active_tokens_for` ignores the explicit `now`; D2 it returns inactive tokens; D3 an empty roster gets the shape message; D4 the empty-roster text changed (4 killed); D5 a non-mapping roster accepted (survived the PR's file).
- incident-replay engine.py `render_markdown`: M1 agent-not-found line removed; M2 empty-grants line removed; M3 empty-timeline line removed; M4 manifest placeholder removed; M5 token id not truncated; M6 timeline timestamp not truncated; M7 agent branch inverted; M8 owner line dropped. All 8 killed.
- kill-switch `_parse_method`: K1 two known verbs, first picked; K2 an unknown verb accepted; K3 `HTTP` prefix tokens not dropped; K4 slash not a separator (4 killed); K5 lower case not folded (survived the PR's file).
Totals counted from the lists: 36 valid mutants; 31 killed by the PR's six files; 5 survived them (A6, U4, U5, D5, K5). The 5 survivors run against each service's whole suite (claude-approver 325, delegation-authority 259, kill-switch 277 at baseline): U5 killed (38 failed), D5 killed (1 failed), K5 killed (1 failed): those three are covered by older tests; A6 still survives (325 passed) and U4 still survives (325 passed). A6 is equivalent (the `{`-prefix guard is redundant: an inline JSON string is never an existing file, so `is_file()` is False either way). U4 is a true gap: a cursor entry whose value makes `int(...)` raise `TypeError` (for example `{"s1": {"input_tokens": null}}`) is only classified "corrupt" thanks to the `TypeError` clause; no test supplies one. Every mutant of a behaviour the PR names (render_pdf, field_ids and the AGENT_MAP precedence, the cursor shape checks, the explicit `now` and the empty-roster message, the markdown sections and the verb parser) is killed by the PR's files.

## Findings
- F-LANER-1 LOW: U4, add one cursor case with a null or list value inside a snapshot.
- F-LANER-2 LOW: A6 equivalent, nothing to do.
- F-LANER-3 note: objection 1; if the author lists the 11 mutants, I can check the ones I did not rebuild.

## Verdict: PASS on 2b1b23b3c6cf84b377dc86512877b81a0d138957
Head frozen; LOWs go in a NEW PR. Tests only, so a docs-style light run is not allowed (the PR adds code); CI green and the full GX10 run on this exact head rebased on current main per the coordinator procedure. Not run by me: CI, GX10.
