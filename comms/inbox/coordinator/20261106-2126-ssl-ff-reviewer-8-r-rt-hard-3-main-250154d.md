# R-RT-HARD-3: adversarial hardening review of merged G24: tools/stage_controller.py and its records (reviewer ssl-ff-reviewer-8)
Head attacked: main 250154d3f (contains the merged G24 with the PR 826 and 832 fixes). I attack, I do not fix; nothing was pushed to any PR or to main.
Prior art not repeated: red-team files 20261106-0230, 0340, 1000 (F-816-1..5, RT-832-R1..R4). Also checked: my own F-R8-1 (below).

## VERDICT: no way found to start Stage 2 or Stage 3 without the records and the go sentence the code asks for; 2 MEDIUM gaps in what the controller does AFTER a failure or when run twice, 1 MEDIUM-LOW and 1 LOW on the inputs

Probes: hard3_probe.py and sc_probe.py in my scratchpad (fake driver, temporary records files, no estate). All results below were run on main 250154d3f.

## Verified fixed
- F-R8-1 (my earlier finding: a records write failure inside the abort path stopped the rollback midway): FIXED on main. With the records file raising OSError from the 2nd, 4th and 5th append, the run now returns `aborted_rolled_back`, runs every rollback step in order and sends one `stage_aborted` alert (probe scenarios A, B, C; baseline D unchanged).

## Findings

### F-H3-1 MEDIUM (confirmed): after "ROLLBACK FAILED ... act by hand" the controller starts the stage again without anyone saying the hand work is done
Probe: a Stage 2 run whose first rollback step raises: result `rollback_failed`, rows end `stage_start, step_done, abort, rollback_failed`. A second live `Controller(records, driver).run(2, go_sentence="go", live=True)` straight afterwards returns `completed` with steps `write_override`, `recreate_killswitch`. `preconditions` checks the alerts record, the gate records, the clean-stage rule and the go sentence only; it never reads a `rollback_failed` (or an unfinished `stage_start`) row for the stage it is about to arm. The alert text says the controller "stopped: act by hand", the runbook says a failing rollback "stops the controller: it is never retried and never loops"; a new run is exactly a retry, over an estate in an unknown half-rolled-back state.
Fix direction: refuse a stage whose last record is `rollback_failed` (reason `rollback_failed_unresolved`) until a `record ack-rollback --stage N` row exists, and test the refusal.

### F-H3-2 MEDIUM (confirmed): nothing stops two live runs at once
Probe: two controllers on the same records file and two drivers with 150 ms steps, B started 50 ms after A: both return `completed` and both executed `write_override` then `recreate_killswitch` (so each stage step ran twice on the estate, in an interleaved order). The records show two `stage_start` rows; `stage_clean` reads "last word", so the interleaving can leave a clean or unclean verdict depending on arrival order. There is no lock and no "in progress" refusal (the same unfinished-`stage_start` check as F-H3-1 would give one).
Fix direction: refuse a run when the last row for the stage is a `stage_start` with no terminal row (`stage_in_progress`), and take an exclusive file lock on the records file for the duration of a live run.

### F-H3-3 MEDIUM-LOW (confirmed; design): the go sentence is any non-empty string
`preconditions(2, records, go_sentence=s)` accepted `"x"`, `"go"`, `"no"` and `"."` (probe). It only requires a non-blank string of at most 500 characters that passes the alert content check; only its length and an 8-hex hash are recorded. So the controller cannot tell Don's decision from a script that passes `"go"`: the control is the input path, not the controller. Fix direction: require a fixed form that binds the decision, for example `GO STAGE <n> <sha8> <row count>` (the runbook already types the operators-file sha16 and the row count into the Stage 1 go sentence), and refuse any other text.

### F-H3-4 LOW (confirmed): records never expire, and a back-dated row counts
Probe: a records file holding three hand-written rows dated 2019 (`alerts_proven`, `gate G22`, `gate G18`, no `sha8`) satisfies the Stage 2 plan. `gate_ok` and `alerts_proven` use `any()` over all rows and ignore `ts`; there is no way to withdraw a record (a later `ok: false` row does not cancel an earlier `ok: true` one), so a gate that was true once stays true after the estate regresses. RT-832-R1 covers the missing sha binding; this adds age and revocation. Fix direction: a freshness window per gate (for example G18 and alerts within 24 h of the run) and last-row-wins semantics per gate, as `stage_clean` already uses.

## Held up under attack (HIGH, probed or read)
- A run is a dry run unless `live=True` AND a driver is given; the CLI has no `run` verb; `record` and `plan` only write their own rows.
- A failed gate row (`ok: false`) does not satisfy a gate; a record on another build sha is refused when `--build-sha` is given (RT-832-R1 stays the opt-in gap).
- `stage_clean` reads the last word for its stage: a later `stage_start`, `abort`, `rolled_back` or `rollback_failed` of Stage 2 makes it not clean.

## Not checked (stated)
`tools/phase_g_check.py` beyond the `--stage 2` entry check (reviewed in PR 827); the real driver (it is not in the repository); file permissions and a symlinked records path; torn or interleaved appends under a crash; the CLI argument parser for odd `--stage` values.

## Suggested builder cards (the coordinator adds them)
1. G24: refuse a stage after `rollback_failed` or an unfinished `stage_start`, plus `record ack-rollback`; exclusive lock for a live run (F-H3-1, F-H3-2; tests with a failing rollback then a second run, and two concurrent runs).
2. G24/G25: a bound go-sentence form (F-H3-3) and per-gate freshness and withdrawal (F-H3-4); decide together with RT-832-R1/R2 (always pass the build sha, default the expected services).
