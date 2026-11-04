From builder-N4: B-S3-13 sentinel score failure exits, PR 635

Head SHA: 1c90a41d32864216561e3574478cc144c425822d (fix/sentinel-score-failure-exits-s3-13, draft). UNVERIFIED: no GX10, CI not read.

Claim check: scout evidence true on main (cli.py caught only MeasurementError; provision RuntimeError, httpx errors, OSError, non-JSON /health uncaught) [HIGH]. No open PR or branch covers it: PR 535 is tests only for the other exits, PR 606 is engine body shapes.

Did: cli.py only. One try around health read, provision, run_suite; typer.Exit re-raised first (it is a RuntimeError); fixed-text refusals, exit 1; three clients closed in a finally. New tests/test_score_failure_exits.py (8): 6 red on main, 2 green (the /health non-200 guard and non-JSON /check). Correction to the card: non-JSON /check already ended in a named refusal on main, so it is pinned, not fixed. Three mutants (no typer.Exit re-raise, no close, no httpx.HTTPError branch) each turn one test red. Sentinel suite 271 passed; environment_anchors clean; tools tests 260 passed + 1 known c57 baseline.

Not verified: CI; behaviour against a real estate. Left open: subprocess.CalledProcessError from --ledger-down-cmd is still uncaught (not in the card).

Decisions needed: none.
