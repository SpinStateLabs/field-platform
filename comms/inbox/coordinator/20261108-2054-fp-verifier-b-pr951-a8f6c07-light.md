# Verifier report: PR 951 light run, docs only (fp-verifier-b)

Head: a8f6c07 (exact PR head, fetched from GitHub). Commits behind main: 40 (main 347b72089 at run time; merge base 2bc5643e7). Run on the exact head, not rebased on main.
PR diff vs merge base: STATE.md only (+46/-10). Light run, docs only: not the full 16 suites.

| Suite | This run | Reference | Change |
|---|---|---|---|
| tools doc/state/readme/lint/link/one-liner/dossier subset (-k 'state or readme or doc or lint or link or one_liner or dossier') | 1428 passed, 3 skipped, 2935 deselected | no like-for-like count recorded | not comparable |

The subset was chosen because the tools lints read repository documents. It is a keyword selection, not a proof that no other test reads STATE.md. No failures, no errors. The other suites were not run (no code or test change in the diff).
