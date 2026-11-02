merge assistant 1: batch cb16 pushed, GX10 run NEEDED (both verifiers busy: A on ma3, B on ma2c).

- Branch: batch/2026-11-01-cb16, head 1e663542821534b9cd5651854f3d9a7db22a3a0d, on main 9addf44f71a69148a49fd3b0fe412bf1e3316c05 (read from git ls-remote at build time). 11 commits, six PRs cherry-picked in order, no conflicts. Author and committer on all 11: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- PRs (head read with git ls-remote refs/pull/<n>/head at 19:2x; CI SUCCESS 7/7 via gh pr view):
  - 407 @e256e6b (2 commits): Q-17 PASS WITH CONDITIONS, only blocking C1 = full GX10 run on the rebased batch with the lint file re-run (that is this run): 20261101-1530-reviewer-lane17-q17-pr407-e256e6b.md; earlier GX10 B 16/16 on the PR's own base: 20261101-1550-gx10-verifier-B-pr407.md.
  - 406 @a40e6da (1): C-1055 PASS, no conditions: 20261031-1752-reviewer-c1055-tests-prs-387-388-404-406-407.md.
  - 396 @2d830e9 (1): C-1053 PASS: 20261031-1743-reviewer-c1053-docs-prs-334-335-378-393-396-398.md.
  - 393 @91af42b (3): C-1076 PASS (closes the C-1053 F-C393-1 condition on a newer head): 20261101-0335-reviewer-c1076-prs-363-377-393-408.md.
  - 378 @1519000 (2): C-1053 PASS (same file as 396).
  - 377 @4292a6a (2): C-1076 PASS (same file as 393).
- Needed: a full 16-suite GX10 run on 1e663542 (one at a time, so after A or B is free; request filed in inbox/verifier). On green, fast-forward main 9addf44f -> 1e663542821534b9cd5651854f3d9a7db22a3a0d.
- NOT checked: no test run by me (Windows, no venv); I did not read the six verdict files in full beyond their VERDICT and CONDITIONS lines; no check that the docs PRs' file:line claims still hold on 9addf44f (reviewers read them on older mains); did not check whether PR 393/396/377/378 overlap hunks with ma3 (334, 335, 347) beyond a clean cherry-pick on plain main; no Don ruling search beyond tasks/DECISIONS-FOR-DON as cited by the v2 table (stale, 2026-11-01 06:12Z).
- Not taken: 359 (Lane R), 402, 392, 316, 347 (ma3), 344 (Don HOLD), 391 (conflicts), 387/385 (stacked on compose base), 383/336 (docs/ENVIRONMENT.md, to do commit by commit later).
