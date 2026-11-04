# Reviewer report: PR 346 @ 64fc69f35553c18089881211e041f53129e5f678 (C-564 commit-identity guard; Q-69 pins)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base 5808a5cd (old); 13 commits; 5 files (+1174): tools/check_commit_identity.py (+265), three test files (552 + 118 + 207), .github/workflows/ci.yml (+32, a `commit-identity` job). Author and committer of all 13 = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `git merge-tree --write-tree origin/main pr346` clean (HIGH). Trailers: 7 Sonnet 5.5, 6 Fable 5.1.

## Objections first
1. PROCESS: 6 of the 13 commits carry `Co-Authored-By: Claude Fable 5.1`; the standing rule for every lane is Opus/Sonnet/Haiku, never Fable (HIGH that the trailers are present; MEDIUM that a Fable session wrote them). Coordinator ruling needed; not mine to rewrite.
2. DESIGN GAP (HIGH, run by me): the guard accepts `noreply@anthropic.com` as an "agent no-reply form" (check_commit_identity.py NOREPLY_PATTERNS, docstring "Accepted email forms"). I ran it over PR 352's range, which contains commit 3a525dcc authored and committed as `Claude <noreply@anthropic.com>`: the guard answered "clean (checked 5 commits)", exit 0. So the guard enforces "no personal mailbox", not "the repository identity" (Don Hagell noreply) that the reviewer rule and PROTOCOL.md ask for. That is a scope statement, not a bug, but a reader of the job name may assume more.
3. A regex name rule is a floor: spelled-out forms, homoglyphs and plain user names are out of scope (stated in the docstring, verified); the guard also does not read tags, squash-merge commits or direct pushes (stated).
4. The tool is not on main yet, while comms/PROTOCOL.md already tells every lane to run `python tools/check_commit_identity.py` from a checkout of main (`git cat-file -e origin/main:tools/check_commit_identity.py` fails): until this lands that instruction cannot be followed on main.

## Verified
- Baseline on the exact head: the three test files 284 passed (stdlib + pytest + pyyaml; relative PYTHONPATH `tools`).
- Real runs (mine): the guard over this PR's own range 5808a5cd..64fc69f3: "clean (checked 13 commits)", exit 0; findings print sha and field class only, never the value (code read, and mutant R3/P3 below).
- CI job read: runs only on pull_request, `permissions: contents: read`, `persist-credentials: false`, `fetch-depth: 0`, base ref passed through an env var (no `${{ }}` inside the script), `--require-commits`, optional allow-domain from a repository variable.

## Mutants (scratch worktree on the head; baseline 284 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| N1-N6 | name patterns 1, 2, 3, 4, 5, 7 removed (one each) | 8, 15, 1, 1, 7, 8 failed | yes (6/6) |
| N7 | NFKC normalisation dropped | 7 failed | yes |
| N8 | format characters not dropped | 5 failed | yes |
| N9 | ideographic full stop not folded | 4 failed | yes |
| N10 | empty name accepted | 2 failed | yes |
| E1 | numeric-id no-reply form removed | 202 failed | yes |
| E2 | bare-handle no-reply form removed | 5 failed | yes |
| E3 | github.com merge identity removed | 2 failed | yes |
| E4 | anthropic no-reply removed | 7 failed | yes |
| E5 | any github.com local part accepted | 2 failed | yes |
| E6 | domain match case-sensitive | 3 failed | yes |
| E7 | email fullmatch -> search | 14 failed | yes |
| E8 | allow-domain ignored | 4 failed | yes |
| E9 | allow-domain dot unescaped | 2 failed | yes |
| E10 | empty email accepted | 3 failed | yes |
| T1 | trailers not checked | 36 failed | yes |
| T2 | unknown trailer key echoed | 6 failed | yes |
| T3 | URL token not set aside | 3 failed | yes |
| T4 | @handle token not set aside | 2 failed | yes |
| T5 | committer name not checked | 3 failed | yes |
| T6 | author email not checked | 36 failed | yes |
| P1 | five-column lines rejected | 166 failed | yes |
| P2 | trailers-placeholder check removed | 2 failed | yes |
| P3 | malformed-line error echoes the line | 1 failed | yes |
| P4 | splitlines instead of newline split | 13 failed | yes |
| R1 | --require-commits ignored | 2 failed | yes |
| R2 | findings exit 1 -> 0 | 11 failed | yes |
| R3 | finding text changed | 1 failed | yes |
| C1 | CI: --require-commits dropped | 1 failed | yes |
| C2 | CI: fetch-depth removed | 2 failed | yes |
| C3 | CI: base ref inlined into the script | 1 failed | yes |
| C4 | CI: job runs on every event | 2 failed | yes |
| C5 | CI: persist-credentials true | 1 failed | yes |
Totals counted from the table: 38 mutants (N1-N6 count 6), 38 killed, 0 survived; no survivor to run against the suite. I did not run the other suites (the PR adds one standalone tool, one workflow job and its tests).

## Findings
- F-C564-1 PROCESS: Fable trailers (objection 1).
- F-C564-2 MEDIUM-LOW: objection 2; either state in the job name/README that it enforces "no personal mailbox" only, or add an opt-in `--require-identity` check against the repository identity. Not blocking.
- F-C564-3 LOW: objection 4; the PROTOCOL line that names this tool is ahead of main until this PR lands.

## Verdict: PASS WITH CONDITIONS on 64fc69f35553c18089881211e041f53129e5f678
Conditions: (1) coordinator ruling on the Fable trailers; (2) CI green (note: the new `commit-identity` job will itself run on this PR) and GX10 16/16 on this exact head rebased on current main; head frozen after this PASS, LOWs and F-C564-2 go in a NEW PR. Not run by me: CI, GX10.
