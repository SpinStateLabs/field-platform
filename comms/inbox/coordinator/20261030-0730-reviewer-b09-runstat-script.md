# B-09: runstat, a read-only status line per ~/ff-work/*-all.log (GX10, outside the repo)

Script: `~/ff-work/runstat.py` on the GX10 (python3 stdlib only; `runbatch.sh` and every log untouched; nothing signalled, nothing written). Run it through `mcp__gx10__run_on_gx10`:

```
python3 ~/ff-work/runstat.py                 # every log touched in the last 3 days
python3 ~/ff-work/runstat.py --all           # every log
python3 ~/ff-work/runstat.py c241 batchz     # named runs only
python3 ~/ff-work/runstat.py --json batchz   # machine-readable
```
Exit code: 1 when any shown run has a failed test, an error, a suite with no result line, or a DEAD runner; 0 otherwise (so a script can gate on it).

## What it prints, per run
`run, suites, passed, failed, errors, runner state, log age`, plus up to three offending suite names. Source of each number: the log's own `== <suite>` blocks and the last pytest line under each (the format `runbatch.sh` writes). `passed` is the sum over suites; `failed` and `errors` likewise; a suite with no result line counts as one error unless that run is still running and it is the last block (then it is shown as `running: <suite>` and not counted).
Runner state: `running` (a process whose command line is `runbatch.sh <name>` / `run*.sh <name>`, or a pytest under a `wt-<name>`/`<name>` directory), `done` (the `<name>-all.done` marker exists and no such process), `DEAD (no marker, no process)` (killed or crashed run: no marker, nothing alive), `queued (a waiter shell holds it)` (a `while pgrep -f ... ; ... runbatch.sh <name>` shell, which my first version wrongly read as running), `done, process still present`.

## Observed now (main 1bae4fa era, 103 logs)
- Most runs: 16 suites, 0 failed. Latest full runs: batchz 6240 passed, c304 6239 passed.
- Runs with a failed test (all marked done or DEAD, none running): c161 (delegation-authority 1 failed, DEAD at 11 of 16 suites), c285 (tools 1 failed), pgc-c122 (tools 4 failed), renew-token-c30 (tools 3 failed), rr (tools 1 failed and 75 errors, DEAD at 2 suites). Each of the first four has a later re-run that is clean (c161b, c285r2, pgc-c122b, renew-token-c30b); I did not open those failures.
- DEAD runners (no marker, no process): batchi, c129, c161, c178, c178r2, c207, mv, rr. Each is older than 10 hours.
- Running when sampled: batchaa (field-agent / agent-registry stage), c325 (tools stage).
HIGH for what the logs and `ps` showed at that moment; it changes by the minute.

## Limits
- A process match is by name in a command line: a run started under another name or without the name in its command line shows DEAD while it is alive. MEDIUM.
- It cannot tell a hung runner from a slow one (no timestamp per suite is written by `runbatch.sh`; age is the log's mtime). Unknown.
- It reads only `*-all.log`; the extra logs (`b10-*`, `*-core.log`, `*-tools.log`) are ignored.
- It does not read my own per-session logs (`c263-pinned.log` etc., which have no `-all` suffix).

## What I did NOT do
- Edit `runbatch.sh`, the repo, or any log; kill or restart a runner.
