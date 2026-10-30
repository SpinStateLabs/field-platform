VERDICT: PASS WITH CONDITIONS on 5d5cbf733c73875f279f6a47dca00ac9be157eaa  (UNVERIFIED: cloud reviewer, no GX10, no docker, CI not read)

C-798, PR 353 after C-735 (PASS WITH CONDITIONS on the same SHA). The head has not moved since C-735 (5d5cbf7; the card's earlier head was 783a85f). So no C-735 condition can have been closed by new commits on this PR; I re-probed each. This SHA only. Note: the card says "exit codes 0/1/2"; the tool's contract is 0 clean, 2 refused, 3 could not (never 1), per its docstring.

OBJECTIONS FIRST
1. C-735 F-C735-3 (lexical `..` before a link is followed) is OPEN and fail-open under `--realpath`. Probe (temporary tree, model files, the CLI): a source `<repo>/link_out/../data/f`, where link_out is a symlink to a directory outside the repository, exits 0 (clean) with `--realpath`; the same for `<repo>/link_etc/../x` with a link to a system directory. The kernel resolves them to the parent of the link target, outside the repository. A plain source through the link (`<repo>/link_out/data`, `<repo>/link_etc`) exits 2 under `--realpath` as intended, and exits 0 without it, as the docstring says. `docker compose config` cleans paths lexically, so this is unreachable through `--run-compose`; it is reachable through a model file or stdin. Confidence HIGH (observed).
2. F-C735-2 (non-string values read as clean) is OPEN. check_model on a model where a secret's `file` is a list, `driver_opts.device` is a list, `build.context` is a list, a service is a string or a list, or `env_file` has `path: 5`: all return no problem (exit 0). The docstring promises exit 3 for "a bind source that is not a string". Only service volume sources are covered. Confidence HIGH (observed). (PR 370 closes part of this for build contexts; this head does not.)
3. F-C735-1 (allowed root behind a symlink is refused under `--realpath`) is OPEN. Probe with the allowed root replaced by a symlinked directory: a source under it is allowed without the option and refused with it. Fail-closed, but it pushes an operator to drop the option that stops symlink escapes. Confidence HIGH.
4. An empty service map exits 0 with "every bind source is allowed" at this head (probe: `{"services":{}}` gives exit 0); PR 370 changes it to exit 3. A wrong -f file is a clean pass here. Confidence HIGH.
5. Root handling: `--repo-root` as a symlink to the repository works (the source under the real path and under the link path both exit 0 with `--realpath`); a root that does not exist, `.`, `/` and the empty string exit 2 (every source refused, fail-closed); `/tmp` exits 0 for a source under it (the operator's trusted argument, as stated in the docstring); a trailing slash or a `sub/..` suffix on the root is normalised and works. A root outside the repository is not detected as such (it is the operator's word). Junctions: Windows only, not probed. Confidence HIGH on the Linux results.

ASSUMPTIONS
A1 Card scope: each C-735 condition, whether the head closes it, exit-code separation, symlink and junction roots, a root outside the repo. A2 The tool is run by an operator on a model from compose or a file.

REASONING / CHECKS
- C-735 conditions: (a) F-C735-1 root behind a symlink: OPEN. (b) F-C735-2 non-string shapes: OPEN. (c) F-C735-3 lexical `..`: OPEN. (d) F-C735-4 pin gaps (16 of 86 mutants survive, 8 real): not re-run; the head is unchanged, so they stand. Also C-735 items 5 and 6 (posture not checked; script run from a copy fails with ModuleNotFoundError): unchanged.
- Exit separation, probed through the CLI: a clean model 0; refused source under `--realpath` 2; missing model file 3; no arguments 3; unknown flag 3; JSON list 3; non-UTF-8 file 3; `--run-compose` with a missing file or no docker 3; `--help` 0. Never 1 on any of these (HIGH). So the 0/2/3 separation holds; argparse's own code 2 is mapped to 3.
- Tests at this head: tools compose tests (c512, c638, static pins): 921 passed.
- Commits: stack of four ending at 5d5cbf7, author and committer Don Hagell no-reply on all. No estate address, flag value, credential or deploy status found in the diff of the tool and tests.
- Mutants: not re-run (C-735 ran 86; I did not verify its 70 of 86 count).

CONDITIONS
C1 (non-blocking, the PR is not changed) F-C735-3: call realpath on the original string, or refuse a source containing `..` when `--realpath` is given.
C2 (non-blocking) F-C735-2: `must_be_text` for secrets, configs, driver_opts.device and build contexts; exit 3 for a service that is not a mapping.
C3 (non-blocking) F-C735-1: resolve the allowed roots with the same function under `--realpath`.
C4 (note) PR 370 (C-787) builds on this head and carries the empty-model fix and part of C2.

NOT VERIFIED
GX10 full set, CI, a real `docker compose config` output, Windows junctions, the 86-mutant run, the 8 real pin gaps individually.

CONCLUSION
The exit contract (0, 2, 3, never 1) holds on every input I fed it. The three C-735 findings stand unchanged because the head has not moved: one is a fail-open under `--realpath` that is unreachable through the compose path. PASS WITH CONDITIONS, UNVERIFIED.
