# Reviewer (lane B, federation-broker): PR 501 (scout P-19) `keygen` 0600 and no overwrite without --force

**Verdict: PASS WITH CONDITIONS on head `49a11e76c2b5f770d83400df8bf722478e347d08`.** Head unchanged at start and end (git ls-remote); base main cd3b7690; 1 commit, Don Hagell noreply author and committer. Not built by this lane.

Diff: `federation_broker/cli.py` keygen (+23/-2): refuse if either PEM exists unless `--force` (exit 2, names `--force`, no key text); private key opened `os.open(..., 0o600)` with O_EXCL (O_TRUNC under force) then `chmod 0600`; public written after. Tests: new `test_keygen_hardening.py` (8). HIGH (read from the diff).

## Objections first
1. `--force` over a symlink: O_TRUNC and chmod follow it, so the key is written through to the target (LOW, no test, not claimed).
2. The public PEM is written with `write_text` and no O_EXCL: a file created between the precheck and the write is silently replaced (LOW, race; the private key has the O_EXCL guard, the public does not).
3. A failure after the private file is created leaves a private key with no public key (LOW).
4. Windows: `os.chmod(0o600)` only toggles read-only; the mode claim is POSIX-only and the tests skip on win32 (stated in the PR).

## Measured (GX10, ~/ff-work/wt-ln501, load 0.5, relative PYTHONPATH, own venv with typer)
New file 8 passed. federation-broker suite: PR 199 passed, main cd3b7690 191 passed (+8, no count down). CI at the time of review: 1 SUCCESS, 6 with no conclusion yet (pending), so NOT 7/7. 16-suite not run by me.

## Mutants (29; source restored after each, worktree clean)
| Behaviour pinned | Killed | Survived |
|---|---|---|
| B1 private key 0600 | 5 | 1 (creation mode 0o644: equivalent, the later chmod sets the end state) |
| B2 refuse overwrite without --force | 4 | 2 (precheck only public and always-O_TRUNC: equivalent, the other guard covers; the O_EXCL race branch has no test) |
| B3 --force replaces the pair | 4 | 1 (**force keeps the OLD public key: real gap**) |
| B4 no key material printed | 3 | 1 (**success path prints the private PEM: real gap**) |
| B5 either file blocks, none written | 3 | 1 (check only public: equivalent, O_EXCL refuses the private) |
| B6 a fresh name is not blocked | 4 | 0 |
Totals counted from the table: killed 5+4+4+3+3+4 = 23; survived 1+2+1+1+1+0 = 6; 29 mutants. Of the 6 survivors, 4 are equivalent or redundant-guard (B1, both B2, B5); 2 are real unpinned behaviours (B3, B4).

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (6 of 7 checks had no conclusion when read).
- C2: GX10 16-suite 16/16 on a head containing main, and a re-run after a rebase if PR 464 (also edits federation_broker/cli.py, different functions) lands first.

## Findings (non-blocking; optional LOWs go in a NEW PR, head stays frozen)
- F-501-1 LOW: no assertion that `--force` replaces the PUBLIC key (survivor B3: an old public key left beside a new private key would pass every test). One line in test_force_replaces_the_pair.
- F-501-2 LOW: no test that a successful run prints no private key text (survivor B4; only the refusal is guarded).
- F-501-3 LOW: the O_EXCL / FileExistsError branch and the public write race are untested (objection 2).
- F-501-4 LOW: symlink under --force writes through (objection 1); consider `os.path.islink` refusal.
- INFO: PR body says "Cloud, UNVERIFIED until a GX10 run": this report is that run for the keygen tests and the service suite only.
