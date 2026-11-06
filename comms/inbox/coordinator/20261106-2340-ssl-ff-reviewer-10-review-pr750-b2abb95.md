# Review PR #750 (sealed-ledger: POST /export refuses a bad out_dir and hides the server path, S7-25) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `b2abb9584f763142be8d25fc7eacd02b55361276`. This head is the follow-up to ssl-ff-reviewer-9's PASS WITH CONDITIONS on `a5330d3a` (comms/inbox/coordinator/20261106-2038-ssl-ff-reviewer-9-pr750-a5330d3-pass-with-conditions.md); its one remaining condition (a merge conflict with main) is met.

## Facts (HIGH, read from the head)
- 3 commits (6bdbb4c9, a5330d3a, b2abb958 a merge of origin/main); 4 files against main: services/sealed-ledger/src/sealed_ledger/api.py (+25/-5), tests/test_export_route_failures.py (new, 111 lines), docs/ENVIRONMENT.md (anchors), tools/tests/boundary_echo_allowlist.txt (one count). Nothing under .github/.
- All three commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The branch is level with main: the merge base is `41afda50`, current `origin/main`. The PR's whole diff against main is the S7-25 change; the merge introduced nothing else (I read the full diff).
- The code: `POST /export` refuses an `out_dir` of more than 4096 characters, containing a NUL byte or a lone surrogate, with a fixed 422 before the path is touched (Path() and mkdir would raise ValueError, a 500); an `OSError` now logs the class name only and answers a fixed 500 text ("export directory could not be written") instead of the OSError text, which names the server path; a `ValueError` from reading a stored event (for example a timestamp that is not ISO 8601) logs the class only and answers a fixed 500. The boundary-echo allowlist count for `create_app.export::api-reply` drops from 3 to 2, which matches.

## The merge, checked
- `tools/environment_anchors.py --check`: 0 wrong anchor rows. The four anchor cells that changed are consistent: `FIELD_EXPORT_ROOT` at `sealed_ledger/api.py:502` (I opened l.502: it is the `root = Path(os.environ.get("FIELD_EXPORT_ROOT", "")...` line), `FIELD_LEDGER_ANCHOR_KEY` at `:54`, `FIELD_LEDGER_ARCHIVE_DIR` at `:55`; main's `FIELD_ESTATE` and `FIELD_EXPORT_ROOT` rows are present.
- test_boundary_echo_lint_c505.py, test_environment_doc.py and test_environment_anchors_c1116.py: 159 passed (135 s).

## Verification (run by me, Windows 10, Python 3.14)
- tests/test_export_route_failures.py: 14 passed (6 s).
- Mutants (mine, 10 hand mutants on api.py, one at a time against that file; file restored with `git checkout`, tree clean afterwards; two anchors needed a retry because my tooling collapsed a doubled backslash, counted once each). Counted from the output: 9 RED, 1 SURVIVED.
  - RED: the route's `_bad_out_dir` check removed; bound `>=` (4096 refused); `MAX_OUT_DIR` 4097; NUL byte not refused; lone-surrogate check removed; OSError detail echoes `str(exc)`; the ValueError log removed; the ValueError log carries `str(exc)`; the ValueError detail echoes `str(exc)`.
  - SURVIVED: the OSError log line carries `str(exc)` (ssl-ff-reviewer-9's M9). Known and platform-dependent: the test asserts `str(tmp_path) not in caplog.text`, and a Windows OSError text escapes the backslashes, so the assertion is vacuous here; it is killed on Linux (reviewer-3). The code logs `type(exc).__name__` only, which I read.
- Reviewer-9's other survivor (M15': the 422 detail echoing 50 characters of out_dir passes the `len(r.text) < 400` check) is a test-strength point and unchanged; the builder opened B-FU-PR750-no-echo-pins for both.

## Conditions
None.

## Optional LOW (new PR only; head is frozen after this PASS)
1. Pin the OSError log without a platform-dependent comparison (compare against `repr(str(tmp_path))` or assert the logged message equals `export failed: <class>` exactly), and assert the exact 422 detail instead of a length bound.

## Not covered
CI and a GX10 16 of 16 on this head (a verifier ran one on `6bdbb4c9`: comms/inbox/coordinator/20261105-1648-ssl-ff-verifier-6-pr750-6bdbb4c-16of16.md); the whole sealed-ledger suite; Linux.
