VERDICT: PASS WITH CONDITIONS on fae8cc0a2d7ea8f051d0f43c403d89860943e1d8

Reviewer Lane 15, cloud-reviewer, C-945, PR 391 (one new commit, fae8cc0, on PR 387's head d4902a0; 5 files, +130/-11). UNVERIFIED: no GX10, CI not read; scratch tree.

## Objections first
1. Merge-order conflict, not a code fault: PR 391 and batch BZ2 (PR 389) and batch BZ (PR 386) all carry the same bind-source commit (patch-id equal: 7679259 in 391's stack, f7baaab in 389, ab39a0f in 386). merge-tree of 391 with 389 and with 386: conflicts in tools/compose_bind_rules.py, tools/compose_resolved_check.py, tools/tests/test_compose_resolved_bind_c512.py and tools/tests/test_compose_static_pins.py. Clean with 328, 345, 353, 370, 385, 387, 379, 342, 381, 383 and main. Whichever stack lands first, the other must be rebased (git drops the duplicate), not merged (HIGH, run). BZ2 also carries the runbook soak commit; it touches the same runbook file but no conflict was reported with 391 for that file.
2. The runbook note sits after the command it claims to precede. Step 9's `docker compose $F up -d ... --force-recreate` line comes first (docs/runbooks/v1.2-deploy-rollback.md:164-165), then "Optional operator check before this step" (:166-170). A top-to-bottom reader runs the up command before reading the check. The pin only requires the note to come before the `--force-recreate is required` sentence, not before the command (test_the_runbook_names_the_check_as_optional ... index comparison). MEDIUM (wording, HIGH read).
3. "Copied alone" guard covers one failure: a missing or stale sibling (ImportError, ModuleNotFoundError) gives exit 3 and a message. A sibling that exists but raises any other error still dies with a traceback and exit 1 (probe: a sibling that raises at import: exit 1). `--help` on a lone copy is exit 3 too, with no usage text. LOW (HIGH, run).
4. The honest bridge message is exact-match only: `network_mode: Bridge` and `network_mode: bridge ` (trailing space) are still refused (exit 2) but with the old "joins another namespace" wording, which is the wrong explanation the commit set out to remove. Whether compose can emit those spellings in `config` output is not known to me (MEDIUM). LOW.
5. Behaviour change: `network_mode: bridge` is now refused on purpose in both layers (it was already refused, with the wrong text). Any compose file or environment that spells the default out explicitly is refused. The tree's compose files use `none` only (3 in the GB10 overlay) and the static pins pass, so no shipped file is hit (HIGH, grep and run).

## What the copy-alone case guards against
Copying tools/compose_resolved_check.py to another host (the operator's machine, the estate host) without compose_bind_rules.py: before this commit that was a Python traceback and exit 1, outside the documented exit contract (0 clean / 2 refused / 3 could not check). Now exit 3 with "keep the script next to tools/compose_bind_rules.py (copy both files, or run it from the checkout)". Probes: alone (stdin, file argument, --help): exit 3 with that message; with a stale sibling lacking the new function: exit 3; with a sibling: works; via symlink: works (HIGH, run).

## Runbook text: public safety
Added lines contain no address, flag value, build id, host name, home path, e-mail or deploy status (sweep count 0; the lines name only `$F`, `<checkout>` and tool paths) (HIGH, run). The claim "nothing in this repository or in CI runs it" is true: the only non-test files naming compose_resolved_check are its own file, compose_bind_rules.py and the runbook; no workflow or script references it (HIGH, grep). The command `docker compose $F config --format json` is a Compose v2 invocation; whether the estate's Compose version supports `--format json` I did not verify (MEDIUM, general knowledge).

## Overlap in files
- Against PRs 328, 385, 387: 391 contains them in full (385 and 387 are ancestors of its head); only fae8cc0 is new.
- Against BZ2 (389) and BZ (386): see objection 1.
- New-commit files: runbook (+5), compose_bind_rules.py (+12), compose_resolved_check.py, test_compose_static_pins.py (8 lines), new tools/tests/test_compose_wiring_c932.py (96 lines).

## Evidence
- 1089 tests pass over the wiring, static pins, bind, c638, c715, c823, c817 and deploy-docs files (HIGH, run; a first run with a missing import path showed 7 failures, which were my environment, not the PR).
- Mutants on the new code: 9 applied, 9 killed (import guard off, exit code 1, bridge branch off, bridge for any option, `none` refused, resolved layer on old message, static layer on old message, message wording changed, header claim changed). Files restored; worktree removed.
- Author and committer: the no-reply Don Hagell identity on the new commit.

## Conditions
1. Reorder step 9 so the optional check precedes the up command, and pin that order. Non-blocking.
2. Decide the merge order of the two stacks (objection 1). Blocking for merge mechanics only.
3. Catch any exception on the sibling import, or state that only a missing or stale sibling is covered; extend the bridge message to a trimmed, lower-cased match (low).

Not verified: CI, GX10, `docker compose config` output with an explicit bridge, Compose version support for the runbook command.
