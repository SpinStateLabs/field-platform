# Builder Lane 11: B-25, a discovery version of the GX10 batch runner

Claimed on comms. `~/ff-work/runbatch.sh` is NOT edited (every lane's runs depend on it). The new script is `~/ff-work/runbatch-discover.sh` on the GX10, md5 c197c77cc4488a0da1a83292e318414e; a copy is next to this report (`20261101-0600-builder-lane11-b25-runbatch-discover.sh`). Swapping it in is your call: either use the new name, or `mv runbatch.sh runbatch.sh.old && cp runbatch-discover.sh runbatch.sh`. Usage is the same: `runbatch-discover.sh NAME` (worktree `~/ff-work/wt-NAME`, log `~/ff-work/NAME-all.log`, done file `~/ff-work/NAME-all.done`); `runbatch-discover.sh NAME --list` prints the suites it would run and runs nothing.

## What it does differently

- Suites are found, not listed: `core+sealed-ledger`, `tools`, `field-agent` (the three names kept, so existing done checks and logs read the same), then every other `packages/*/tests` and `services/*/tests` alphabetically. The planned `services/field-mcp` suite becomes the 17th with no edit.
- Same log shape: one `== <suite>` line and then the pytest summary line per suite, done file at the end.
- Loud failures, each a line containing `ERROR` (a done check that greps `failed|error` sees it): a tests directory with no `test_*.py`; a `packages/*` or `services/*` directory with `src` but no `tests` directory; a pytest exit code other than 0 or 1 (for example 5, nothing collected).
- Optional `RUNBATCH_DEFENCE=1` adds every `defence-shield/*/tests` suite, with that package's `src` on PYTHONPATH.

## Proofs (all on the GX10, no docker, one full run at a time)

1. `--list` on a worktree of main acaf5f2 gives exactly the 16 hardcoded names in the same order (diffed). With `RUNBATCH_DEFENCE=1` it adds a 17th, `agent-incident-retro`.
2. A synthetic tree (stub suite `zz-stub`, a failing suite, an empty tests dir, a `src`-only service, a tests file that collects nothing): 9 suites, `zz-stub` discovered, `zz-fail` recorded as `1 failed`, and `ERROR` lines for `zz-empty` (no test file), `zz-nosuite` (no tests directory) and `zz-notests` (pytest exit code 5); done file written. (The first attempt showed an error on `core+sealed-ledger` that was my fake tree's own duplicate file name, fixed before the run reported above.)
3. Both scripts, full runs on the same commit (main acaf5f2), compared line for line after removing the timings: identical, 16 suites, 0 failed|error each: core+sealed-ledger 1924, tools 3255, field-agent 153, agent-registry 304, attestation-reporter 135, claude-approver 282, compliance-crosswalk 353, conformance-sentinel 260, delegation-authority 213, federation-broker 105, force-gateway 447, incident-replay 91, kill-switch 160, lifecycle-manager 224, ops-console 300, spend-governor 242.

## A finding you should know

`runbatch.sh` has never run `defence-shield/agent-incident-retro/tests`. So no lane's "GX10 16 suites, 0 failed" covers that suite (I said so in my own B-23 report for its `test_evidence.py`, which I ran locally: 18 passed). `RUNBATCH_DEFENCE=1` adds it; it is off by default so the default stays 16 as the card asked. Say if you want it on by default.

## Limits

A suite that needs a PYTHONPATH beyond the shared src directories (only defence-shield gets its own, via the flag); `core+sealed-ledger` stays one name for compatibility, so a new top-level suite under `packages/*` or `services/*` is found but a new `tools`-style directory elsewhere is not; the synthetic tree in proof 2 is not a git worktree and exercises the script's branches, not a real repository.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
