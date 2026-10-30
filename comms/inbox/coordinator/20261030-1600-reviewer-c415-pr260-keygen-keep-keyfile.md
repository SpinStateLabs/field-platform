# C-415 reviewer report (Lane 5): PR 260 @3e826fd (C-412; my C-408 F-C408-1/-2/-4), production change in tools/operator_keygen.py

VERDICT: PASS on the exact head 3e826fd (one commit on 5ba12004, author and committer Don Hagell noreply; main is c6dc449). The invariant "the key file exists exactly when the registry row landed" held at every injected failure point (15 of 15 cases, both an interrupt and an ordinary exception where both apply), the lock was free after every case, and key-file open errors are now `error:` exits. 92 tests passed on the head (76 on the base). 15 of 16 hand mutants killed; the survivor is effectively equivalent. Two LOW findings and one carried-over item. No key value was printed or kept: every run used a temp directory, removed afterwards, and no probe output contained a key.

OBJECTIONS FIRST
1. F-C415-1 LOW (PROVEN): when an interrupt lands after the registry file was replaced, the key file is now kept (correct) but the run ends with a bare traceback and no word that the row landed and the key file was kept; an operator who sees `KeyboardInterrupt` cannot tell from the output whether the row exists or the key file is usable. The docstring says so (tools/operator_keygen.py, the recovery bullet), and `status` of the registry shows it, but the run itself is silent. Suggest one stderr line in the handler's keep branch ("the row for X was written; the key file Y was kept"). [HIGH, run]
2. F-C415-2 LOW (PROVEN): `_hash_registered` (operator_keygen.py:77-84) tests the run's key hash as a substring of the registry bytes; my mutant that tests only the first 8 hex characters survives. A 64-hex substring cannot appear by chance, an 8-hex one in practice cannot either (32 bits against the handful of rows), so this is equivalent in effect, but nothing pins the full-length match. [HIGH on the survivor, MEDIUM on "equivalent in effect"]
3. F-C408-3 (Windows lock branch unrun) is not addressed by this PR and I did not run it: carried, not new. [HIGH]
4. The keep decision reads the registry file after the failure. That is correct under the lock this run holds, but it is a content test, not a step flag: a different run that landed the SAME hash cannot exist (a new random key per run), so it is sound; I note the design so a later edit to the registry format (for example hashing with a salt) re-visits this function. LOW, no action. [MEDIUM]
5. With `--key-file` and an interrupt after the rename, the row is ACTIVE and its key file exists (mode 0600): this is the better outcome than the old one (ACTIVE row, no key anywhere), and it is the card's goal. Without `--key-file` the key is never printed after such an interrupt, as before (documented recovery). [HIGH]

ASSUMPTIONS
1. Own GX10 worktrees (head and base 5ba12004); Linux `flock` semantics; failure injection in-process by replacing module functions on a fresh copy of the module (a seeded registry created through the tool itself in a temp directory), not by signals to a child process. [HIGH]

REASONING
1. Interrupt at every step of `--add-to --key-file`, each with a KeyboardInterrupt and a RuntimeError (the os.replace case is an OSError): results, row landed / key file present / later run:
   - `prepare_entry` raises: no row, no key file, later run OK.
   - the key-file write raises midway: no row, no key file, later run OK.
   - `os.replace` fails before the rename (OSError): `error: cannot write ...` exit, no row, no key file, later run OK.
   - an interrupt on entering `commit_registry`: no row, no key file, later run OK.
   - the registry changed by someone else after the read: `error: ... changed while the key was being made; nothing was written`, no row, no key file, later run OK.
   - an interrupt AFTER the rename (the C-408 F-C408-1 window): row present, key file present with mode 0600, later run OK.
   - an interrupt during the directory fsync (after the rename): row present, key file present, later run OK.
   - an interrupt at the final print: row present, key file present (unchanged behaviour), later run OK.
   The invariant held in 15 of 15 cases; "later run OK" means a second `--add-to` succeeded, so the lock was released on every path. No output line contained a key. [HIGH, run]
2. Key-file open errors: a key file in a missing directory, an existing key file, and a permission failure are `error: cannot write the key file PATH: ...` exits (`SystemExit` with the message, the existing file untouched and not removed, nothing registered); the new tests pin each of them and that a failed open never removes a file the run did not create. The message carries the OS error text and the path, not the key. [HIGH, run and read]
3. Existing tests: two assertions changed, both from `pytest.raises(FileExistsError)` to `pytest.raises(SystemExit, match="already exists")` (the card's intended behaviour change), and one docstring phrase assertion dropped ("With --key-file the key file exists whenever the row does", which the PR deliberately rewrites; a new test pins the new wording and that the old promise is gone). No other assertion weakened. [HIGH, diff]
4. Mutants (16 hand; the four keygen test files as judge, bytecode caching off): killed 15. Killed: `_hash_registered` always False; always True; reads the wrong file; unreadable counted as registered; the handler's condition negated, always removing, never removing, narrowed to `Exception` (an interrupt would then escape without cleanup); the existing-file case re-raising a traceback; its message changed; the OSError branch re-raising; its message dropping the OS text or echoing the exception repr; `O_EXCL` dropped; the lock descriptor close removed (the F-C408-4 survivor of C-408, now pinned). Survived: the 8-character prefix (finding 2). [HIGH, run]
5. Merge and scope: the change is 30 lines in operator_keygen.py; the lock, the format-2 refusal and `commit_registry` are untouched. [HIGH, read]
6. Public-repo hygiene: tests and code only; no values. [HIGH, read]

CONCLUSION
PASS on 3e826fd; C-408 F-C408-1, -2 and -4 closed. Proposed cards (coordinator numbers them): P1 builder LOW, operator_keygen.py: print one stderr line when the keep branch is taken (row written, key file kept), with a test; P2 builder LOW: pin the full-length hash match in `_hash_registered` (a registry that contains only an 8-character prefix of the hash is not "registered"); P3 reviewer or coordinator LOW: the Windows lock run (C-408 F-C408-3), still open.

What I did NOT do: run the full verify or CI (the coordinator's); signal a real child process (the injection was in-process); run the Windows branch; test a network filesystem or a hand edit of the registry during a run beyond the existing snapshot test.
