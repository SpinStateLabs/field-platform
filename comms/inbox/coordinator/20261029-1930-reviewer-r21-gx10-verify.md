# R-21 reviewer report: `comms/tools/gx10_verify.sh` (one-command GX10 verify, C-47 still open)

DELIVERED: `comms/tools/gx10_verify.sh` on the comms branch (not the repo; card C-47 stays with the builder, who can lift it into `tools/`). Runs ON the GX10.

USAGE
  # Windows side: git bundle create x.bundle BASE..REF ; scp x.bundle gx10:/tmp/
  gx10_verify.sh --name NAME --bundle /tmp/x.bundle --ref REF --base SHA [--quick] [--foreground]
  poll:  test -f ~/ff-work/NAME-verify/.done && cat ~/ff-work/NAME-verify/summary.txt
Detaches with nohup; logs per step in `~/ff-work/NAME-verify/`; `.done` marker and `summary.txt` at the end. Work tree `~/ff-work/wt-NAME-verify`, fresh clone of a seed clone (`GX10_VERIFY_SEED`, default `~/ff-work/wt-fieldrev-80b`; the seed must hold the bundle's prerequisite commits), venv `~/ff-work/venv-fieldrev` (`GX10_VERIFY_VENV`). No DB port, no Postgres, no estate, no secret: it unsets FIELD_SHARED_SECRET, FIELD_OPERATOR_*, ANTHROPIC_API_KEY, refuses a work tree outside `~/ff-work/wt-*-verify`.

STEPS (mirror ci.yml `tests` job on main 444e49b, :52-56, :67, :78-84, :76)
  core_services: field-core + sealed-ledger + delegation-authority + spend-governor + kill-switch + federation-broker in one repo-root pytest;
  tools: `pytest -q tools/tests` (8.5 min; skipped by `--quick`, and the summary says so);
  per-service loop (9 services), field-agent, `tools/topology_lint.py`.
  EXTRA (reported, not decisive): defence-shield/agent-incident-retro, because CI does not run it (F-C141-1); it shows its known red test (F-C141-2).
Not covered: the three docker smoke jobs (compose-smoke, fly-image-smoke, compose-upgrade-smoke).

SELF-TEST (GX10, PR 87 head 70fa59f, base b92ec10, `--quick`): core_services 2176 passed, 4 skipped; nine service suites green (232, 109, 74, 160+1 skipped, 208, 185, 66, 171, 101); field-agent 118 passed; topology_lint OK (0 findings, 4 allowlisted); EXTRA defence-shield 1 failed, 112 passed (F-C141-2); verdict "CI-EQUIVALENT STEPS GREEN" with the note that tools/tests was skipped. First attempt failed because the detached re-exec lost its arguments (`set -u` parser consumed `$@`); fixed with `ORIG_ARGS`, re-run green. [HIGH]

CAVEATS
1. The service list is copied from ci.yml by hand; if ci.yml adds a service this script does not. 2. It does not reproduce the Python 3.11/3.13/3.14 matrix (GX10 venv is 3.12). 3. `core_services` runs in one process like CI, so it shares the conftest-collision behaviour CI has.
