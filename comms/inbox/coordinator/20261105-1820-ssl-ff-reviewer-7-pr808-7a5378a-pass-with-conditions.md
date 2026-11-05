# Review PR 808 (field-mcp mutants.py C3 follow-up to PR 795) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `7a5378a84304ed24bd67547a5a59a54762353877`.
Condition 1 (structural): the PR's base is PR 795's branch (`rebuild/pr368-field-mcp-tier1`, head 5dd1a2ac), not main. It cannot land until 795 lands; after that, retarget/rebase, and the single commit's patch-id must be unchanged (below). Condition 2: none else blocks. The script is a dev tool (not run by CI or any gate: `.github` untouched by this commit).

## Checks (HIGH, run by me)
- Identity: 1 commit above 795's head, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. Diff vs the base (795 head): 1 file, services/field-mcp/scripts/mutants.py, +30/-4. 0 files under .github/ in THIS commit. (Against main the diff also shows 795's ci.yml hunk adding field-mcp install + test steps; that is 795's, reviewed there, not a concurrency block, and not part of 808.)
- Code read: baseline run first (exit 2 if red); PYTHONPATH = copy's src + sibling src dirs; kill only on pytest exit 1, other non-zero = ERROR (counts as not killed, run exits 1); MUTANTS_PYTEST_ARGS via shlex. No defect found. LOW: `shlex.split` in POSIX mode eats backslashes in a Windows-style path argument (use forward slashes).
- Behaviour run on the exact head (Windows, PYTHONUTF8=1, </dev/null):
  - `MUTANTS_PYTEST_ARGS=--no-such-flag python scripts/mutants.py K1` -> "baseline is not green (pytest exit 4); no mutant was run", exit 2. Reproduces the PR's claim.
  - `MUTANTS_PYTEST_ARGS=--ignore=tests/test_stdio.py` K3 alone: baseline green (201 passed, 243 s), K3 KILLED, "all mutants killed", exit 0 (9 min total). K1 K3 pair earlier: K1 KILLED.
  - Incidental: an earlier K1+K3 run was cut by my own outer `timeout`; the killed pytest child printed ERROR (not KILLED) for K3: the exit-code>1 rule works.

## Mutants of the script (5 attempted; counts from the table; there is no test file for this script, so "killed" = a visible behaviour change against the control)
| # | mutant | result |
|---|---|---|
| M1 | baseline gate removed (`if False`) | KILLED (bad-flag run no longer prints the baseline message; mutants run, K3 ERROR) |
| M2 | baseline check always True | KILLED (same) |
| M3 | sibling src dropped from PYTHONPATH | SURVIVED (K3 still KILLED, all killed) |
| M4 | MUTANTS_PYTEST_ARGS ignored | KILLED (full suite ran, no usage error) |
| M5 | ERROR folded into KILLED | NOT RUN (my shell syntax error; the ERROR path observed only incidentally above) |
Totals: 5 attempted, 4 executed; of the 4 executed, 3 killed, 1 survived. Fewer than 4 per behaviour: the script has no tests, which I am noting rather than blocking on (a dev tool; the PR says so).

## Findings
1. MEDIUM-LOW, unverified claim: "puts every sibling src on PYTHONPATH, so a missing sibling is not a collect error". On this head with only `src` on the path, the field-mcp suite (-k test_oversize_reply_is_an_error and the sibling-free import check `grep field_core|field_agent|sealed_ledger` in src/tests = 0 hits) did not need any sibling (M3 survived). Whether another test (e.g. test_stdio, which I ignored) needs them I did not determine. The change is harmless either way.
2. LOW: no test for the script itself (red-baseline exit 2, ERROR vs KILLED, args passthrough). A tiny stub-suite test would pin all four.
3. LOW: shlex backslash note above.

## Not verified
The full 40-mutant run (as the PR also says); test_stdio.py (ignored; the PR names it Windows-only failing); CI/GX10 (not applicable to a dev script; no CI step runs it).
