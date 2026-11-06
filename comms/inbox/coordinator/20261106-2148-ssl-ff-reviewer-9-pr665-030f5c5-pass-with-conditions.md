VERDICT: PASS WITH CONDITIONS on 030f5c5d9e50b08a84c4bb4aa1fbc50aca1baed2  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for the Lane O review (PASS WITH CONDITIONS on 3dc30026). The Lane O conditions are met; I found two defects in the code that the PR's claims cover and the tests do not.

R-PR665-030f5c5, PR 665 (S4-17, attestation-reporter: refuse a bad --out and a blank or unbounded org). Applies to this head only. The fetched pull/665/head is 030f5c5d; the condition-fix commit is tests only (git diff 3dc30026..head: one new test file, +103).

OBJECTIONS FIRST
1. The claim "both texts are built first, so a failure writes nothing half-finished" (code comment in cli.py, PR body) is false for a failure of the SECOND write. Reproduction (no secrets; in-process CliRunner, engine stubbed as the tests do, a directory created where board-pack.html goes): `render --no-pdf --out <dir>` exits 2 with `refused: cannot write the pack into --out (PermissionError)` and board-pack.json IS left behind (json left behind: True). The tests block the FIRST file (a directory at board-pack.json), so `assert not (out / "board-pack.html").exists()` is true before any write was attempted and cannot show the claim. A stale or new JSON beside a missing or old HTML is exactly the half-pack the comment promises not to leave. MEDIUM. HIGH confidence (measured).
2. A lone surrogate in `--org` passes checked_org (category Cs is not in {Cc, Cf, Zl, Zp}) and the CLI then crashes: `render --no-pdf --out <dir> --org "a\udcffb"` exits 1 with an uncaught PydanticSerializationError, no output, no files (measured, same harness). The point of S4-17 is that a bad org is a named refusal and never a traceback; a surrogate arrives from a POSIX argv holding invalid UTF-8 (surrogateescape) or a Windows argv. Private-use and unassigned code points (Co, Cn) are also accepted; they serialize, so only the visual claim ("a name you can SEE on one line") is affected. LOW-MEDIUM (the surrogate crash), LOW (Co and Cn). HIGH confidence (measured).
3. org is now stored stripped (`"  Acme Corp "` becomes `"Acme Corp"`) in the SIGNED board-pack.json; the PR flags it as a decision for Don. An org that a caller signed in a previous pack with padding will no longer re-render byte-identical. Not a defect; a decision. HIGH.
4. Base is b963407a, 64 commits behind main. `git merge-tree --write-tree origin/main <head>` is clean (tree id only, no conflict lines); the allowlist line for attestation-reporter `_build` changed in this PR (1 -> 2) and I re-ran the boundary-echo lint on the head (61 passed). HIGH.

ASSUMPTIONS
A1 Lane O's 37-mutant table is the baseline; I ran my own 18 against the head with both test files, and re-ran the surrogate and half-write probes by hand. A2 The CLI harness (engine stubbed with PackEngine) stands for the real CLI.

REASONING / CHECKS
1. Diff read: org.py +34 (checked_org: strip, blank, 200-limit after strip, Cc/Cf/Zl/Zp by position), api.py +5 (422 with the helper's text, no echo), cli.py +16/-3 (org checked first, --out settled before any service is queried, both texts built then written inside a try for OSError), tests +132 and +103, one allowlist line. signing.py untouched. Nothing under .github/. HIGH.
2. Identity: 3 of 3 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core src): whole attestation-reporter suite 321 passed, 0 failed (439 s); tools/tests/test_boundary_echo_lint_c505.py 61 passed. HIGH.
4. Mutants on a copy of the head, both new test files, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| Q1 | limit measured before strip | KILLED |
| Q2 | limit 199 | KILLED |
| Q3 | limit 201 | KILLED |
| Q4 | reported position counted on the unstripped org | KILLED |
| Q5 | inner double spaces collapsed | KILLED |
| Q6 | Cf not refused | KILLED |
| Q7 | Zl not refused | KILLED |
| Q8 | Zp not refused | KILLED |
| Q9 | Cc not refused | KILLED |
| Q10 | non-string / blank check dropped | KILLED |
| Q11 | refusal message quotes the org | KILLED |
| Q12 | --out refusal carries the exception text | KILLED |
| Q13 | write-failure refusal carries the exception text | KILLED |
| Q14 | API 422 detail changed | KILLED |
| Q15 | CLI org check skipped | KILLED |
| Q16 | --out not settled before any service is queried | KILLED |
| Q17 | JSON written before the HTML text is built | KILLED |
| Q18 | write failure not caught | KILLED |

Counted from the table: 18 run, 18 KILLED, 0 SURVIVED, 0 NOT APPLIED. The 8 Lane O survivors (limit 199, length before strip, position, inner spaces, API text, the two exception-text forms, the build-first order) are all among Q1 to Q17 and now die. The mutation gap is not in the mutants but in the two measured behaviours of objections 1 and 2, which no mutant of the existing code expresses. HIGH on the counts.

CONDITIONS
C1 (required before merge, either fix or a stated ruling) make the second-file failure leave no half pack: write both files to temporary names and rename, or remove the first file when the second write fails; and put the HTML-blocked case in the test (a directory at board-pack.html) with the assertion that no board-pack.json exists. Alternatively correct the comment and PR text to say only the first write is atomic. A condition fix is the only push allowed on the head.
C2 (required, small) refuse a lone surrogate in checked_org (category Cs, or any code point that fails `.encode("utf-8")`), with a test: `checked_org("a\udcffb")` raises InvalidOrg and the CLI answers `refused:` with exit 2. Decide whether Co and Cn are refused too.
C3 (standing gate) GX10 16/16 on this exact head rebased on main; not run by me.

NOT VERIFIED
GX10 / Linux, CI, the PDF path (`render_pdf`, not changed), a real engine (the CLI harness stubs PackEngine), API-side behaviour for a surrogate (a query is decoded with replacement, so the HTTP path cannot carry one).

CONCLUSION
The Lane O conditions are met: 18 of 18 mutants die, 321 tests pass, identity correct, merge clean. Two behaviours the PR's claims cover are not true: a failed second write leaves a half-written pack, and a lone-surrogate org still crashes the CLI with a traceback. PASS WITH CONDITIONS: C1 and C2 are the required fixes, C3 the gate. Head frozen except a condition fix.
