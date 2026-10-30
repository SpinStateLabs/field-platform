# C-431 reviewer report (Lane 5): PR 274 @a31f959 (C-423; my C-421 F-C421-1), tests only

VERDICT: PASS on the exact head a31f959 (one commit directly on main 9589c82, which is current main; author and committer Don Hagell noreply). One assertion added in `tools/tests/test_operator_keygen.py` (+1): the key-file refusal text must contain neither `fok_` nor the key. The mutant I named at C-421 (the message echoing the existing file's contents) now goes red. Whole tools suite on the head: 2645 passed, 4 skipped, 0 failed (python -m pytest -q tools/tests, 487 s). One LOW finding: the assertion catches an echo of the whole key or of its `fok_` prefix, not of a part of the key. No key value was printed or kept: test keys only in temp directories, nothing from my probes carried a key.

OBJECTIONS FIRST
1. F-C431-1 LOW-MEDIUM (PROVEN): the new line is `assert "fok_" not in message and key not in message`. It refuses a message that carries the whole key or any text containing the `fok_` prefix. A message that carries the key WITHOUT the prefix (the file contents from character 4 on) or only the last 12 characters survives, and so does a message echoing a digest of the file (a digest is not the key and is harmless; the first two are not). My mutants: echo `open(path).read()[4:]`: survived; echo the last 12 characters of the stripped key: survived. A partial key in an error text is still key material (the last 12 characters of a key shrink the search space), and an error text is what gets pasted into tickets and logs. The signer test of PR 242 (C-389, which I reviewed at C-396) already uses a sliding window: no 4-character window of the secret may appear in the message; that form would kill both survivors. [HIGH, run]
2. The assertion reads `exc.value` (the `SystemExit` text), which is the right place: the previous version read captured output only, and the refusal text never reached it (my C-421 finding). It now sits beside the other message assertions of the same test. [HIGH, read]
3. Tests only, one line: a pass proves the refusal text carries no full key and no prefix-bearing text; it does not prove other error paths of the tool (open failures, the registry write) are free of key text; those are covered by C-412 tests and my C-415 mutants, not by this line. [HIGH]

ASSUMPTIONS
1. Own GX10 worktrees at the head (one for the suite, a separate one for the mutants so the running suite was not edited under it); the suite with PYTHONPATH from the worktree's package, service and defence-shield `src` directories (the venv's editable install points at another checkout); mutants by my runner on tools/operator_keygen.py 84-110 (6 hand; test_operator_keygen.py as judge; bytecode caching off). [HIGH]

REASONING
1. Diff: one line added to `test_key_file_mode_keeps_the_key_off_stdout`, after the existing assertions on the message (`error: cannot write the key file`, the path, "it already exists", "nothing was written"): `assert "fok_" not in message and key not in message`, where `key` is the first key read from the file. Merge base is main's tip, so nothing to merge. [HIGH, read]
2. Mutants of the refusal text (6 hand): killed 3: echo of the whole file contents (my C-421 survivor), echo of its first 40 characters, and the control (the phrase "already exists" dropped). Survived 3: echo from character 4 on (no prefix), echo of the last 12 characters, echo of a SHA-256 of the file (harmless; included to show the line does not over-reach). [HIGH, run]
3. Whole tools suite: 2645 passed, 4 skipped (2522 passed, 4 skipped at C-421's head 20c8c28; main has since gained tests). [HIGH, run]
4. C-421 F-C421-1 is closed for the whole key and the prefix, not for a part of the key. [HIGH]

CONCLUSION
PASS on a31f959 as the card is written (it asks that the refusal text never carry a key and pins the whole-key and prefix cases). Proposed card (coordinator numbers it): P1 builder LOW-MEDIUM, test_operator_keygen.py: replace the two substring checks with "no 6-character window of the key appears in the message" (kills the two partial-echo mutants); keep `fok_`.

What I did NOT do: run CI (the coordinator's); other error paths of the tool; Windows.
