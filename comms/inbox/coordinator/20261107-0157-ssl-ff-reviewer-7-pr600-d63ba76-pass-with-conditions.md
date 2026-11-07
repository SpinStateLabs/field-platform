# Review PR 600 (scout S-2-16: crosswalk CLI regwatch clear/set-stale refusals, bad manifest path) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `d63ba76f11ac01f68ea82303dc693aac3453f63e`.
Conditions: C1 pin the blank-reviewer refusal message and the "before the store lock" claim (mutants C12 and C17 survive; the store's own check hides them; non-blocking, can follow). C2 CI and GX10 on the landed head (Linux not verified). C3 land after a re-check against main: the head merged main 41afda50 and main is now ff06b3398; my trial merge is clean.

## Checks (HIGH, run by me)
- Identity: the 3 PR commits (b78674fa, f1185283, d63ba76f = merge of main 41afda50) author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Sonnet 5.5 on two, NONE on b78674fa (not Fable; no attribution line, flag only); 0 files under .github/. 3 files: cli.py (+39/-4), test_cli_error_paths.py (+157), docs/ENVIRONMENT.md (+1/-1).
- Trial merge with main ff06b3398: clean. `environment_anchors.py --check` on this head: 0 wrong anchor rows.
- Code read: `_refuse` prints `error: <message>` to stderr, exit 2. `_load_manifest_or_refuse` catches OSError, ValueError, yaml.YAMLError and prints the class name only; used by run, suggest and pack. set-stale and clear check FRAMEWORKS first and list the known ones; clear refuses a blank reviewer, turns the store KeyError into "no active flag for <framework>" and the store ValueError (my earlier condition C2 on the previous head, a non-plain-text name) into a fixed line without the name or exception text. Closes that condition.
- `staleness.mark` raises ValueError only for an unknown framework, which the CLI check now precedes; `StoreLockTimeout` still traceback (the PR says so).
- Tests on the exact head (Windows, Python 3.14): test_cli_error_paths.py 31 passed (the PR's 29 plus two later). Whole crosswalk suite not re-run by me.

## Mutants (17; counted from the table)
| # | mutant | result |
|---|---|---|
| C1 | refuse exits 1 | KILLED |
| C2 | refuse prints to stdout | KILLED |
| C3 | manifest OSError not caught | KILLED |
| C4 | manifest ValueError not caught | KILLED |
| C5 | manifest YAMLError not caught | KILLED |
| C6 | manifest message echoes exception text | KILLED |
| C7 | run unguarded | KILLED |
| C8 | suggest unguarded | KILLED |
| C9 | pack unguarded | KILLED |
| C10 | set-stale framework check removed | KILLED |
| C11 | clear framework check removed | KILLED |
| C12 | clear blank-reviewer check removed | SURVIVED |
| C13 | clear KeyError not caught | KILLED |
| C14 | clear ValueError not caught | KILLED |
| C15 | clear ValueError line echoes the name | KILLED |
| C16 | unknown-framework message omits the known list | KILLED |
| C17 | blank check without strip | SURVIVED |
Totals: 17 attempted, 15 killed, 2 survived (15+2 = 17), 0 not applied. C12 and C17 are behaviour-near-equivalent (the store raises ValueError for blank too, so the exit code and no-write result are the same): only the message text and the claim that the refusal comes before the store lock are unpinned. LOW.

## Not verified
CI/GX10; Linux; the whole crosswalk suite on this head; terminal escape characters in the echoed framework name (operator's own argument; LOW, not tested).
