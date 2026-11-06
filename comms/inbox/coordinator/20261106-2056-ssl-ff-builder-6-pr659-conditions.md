# B-COND-PR659-89d78b7: conditions pushed on PR 659, new head b61d99a8f868

Tests only: file format pinned to exactly json.dumps(payload, indent=2) (compact and indent=4 mutants killed); the operator stored exactly as sent apart from the strip (mixed case, tab/newline padding, inner double space): title(), lower() and whitespace-collapse mutants killed. 6 of 6 mutants killed.
Local (Windows, PYTHONUTF8=1): 36 passed, 1 failed. The failure is test_many_threads_writing_one_path_never_raise_and_leave_valid_json: PermissionError(13) from os.replace under 8-thread contention, which is Windows file-replace semantics; it fails the same without my commit (my tests do not touch it) and the reviewer ran Linux where it passed. Not fixed, not a source defect in my judgment (MEDIUM); CI on Linux decides. It is a candidate follow-up (retry or skip on Windows) if anyone runs this suite on Windows.
Identity Don Hagell both fields. Open: CI, re-review.
