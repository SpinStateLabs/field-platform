# Integration demo — the capstone scenario

A deliberately mundane governed agent — an invoicing copilot that reads a
timesheet CSV and drafts invoices — running against the full FIELD
enforcement stack. Every number and event below is synthetic demo data.

## One command

```
./run_demo.sh
```

Verified path: boots all 7 services as local processes (~21 s total on the
build machine) behind **one** path-routed listener, the local counterpart of the
compose Caddy proxy: `http://127.0.0.1:$PORT/registry`, `/ledger`, `/delegation`,
`/sentinel`, `/killswitch`, `/governor`, `/replay` (the prefix is stripped before
the service sees the request, as Caddy's `handle_path` does). `PORT` is optional:
by default the demo takes a free port, so a listener already on 8001-8007 no longer
breaks it; set `PORT=18081 ./run_demo.sh` to choose one (it exits non-zero if that
port is taken or a service is not healthy behind it). The services themselves listen
on free loopback ports that only the proxy uses (`path_proxy.py`, standard library,
127.0.0.1 only; it also refuses the internal key-rotation routes when a request carries
`X-Forwarded-For`, like the Caddyfile). The compose path (`docker-compose.yml` + `Dockerfile`) is
verified on GB10 (aarch64) and in CI (x86_64) and publishes a SINGLE host
port: a Caddy proxy on :8080 path-routes to every service
(`/registry`, `/ledger`, `/delegation`, `/sentinel`, `/killswitch`,
`/governor`, `/replay`, `/gateway`, `/federation`, `/lifecycle`, `/attest`,
`/crosswalk` — thirteen served services; the ops-console dashboard is the
root `/`). Per-service host ports are no longer published — see
`Caddyfile` and `.env.example` for the host-side `FIELD_*_URL` values.

## The scenario (what an evaluator watches)

| Step | What happens | Governance letter at work |
|---|---|---|
| 1 | Manifest validates VALID; agent registered with human owner | I |
| 2 | Controller mints a 1-hour token scoped to `read timesheets`, `draft invoices` | D |
| 3 | Agent drafts INV-001…004; every check + spend lands in the ledger | E + L |
| 4 | Draft 5 arrives with the meter at 96% of the $500 cap → **ESCALATE** `E.spend_threshold`, queued for a human | E |
| 5 | Agent tries `transfer funds` → **BLOCK** `D.scope`; the function body never ran | D + E |
| 6 | Kill drill: killed, verified, restored — ~53 ms measured | E |
| 7 | incident-replay writes the RACI-ready post-mortem (`out/post-mortem.md`) | L |
| 8 | Board pack — attestation-reporter renders JSON+HTML+PDF | all |

Ledger integrity is verified at the end: every event above is on the intact
hash chain.

## Files

- `run_demo.sh` — the scenario driver (verified)
- `path_proxy.py` — the one-port path router `run_demo.sh` starts (pinned by `tools/tests/test_demo_path_proxy.py`)
- `agent/invoicing_agent.py` — the governed agent (`Governor.check` on every
  tool call; spend metered per draft)
- `agent/timesheet.csv` — synthetic input
- `manifests/invoicing-agent.yaml` — fully-resolved FIELD manifest (VALID)
- `out/` — invoices + post-mortem, regenerated each run
- `docker-compose.yml`, `Dockerfile`, `Caddyfile` — compose path, single
  published port :8080 (GB10 override: 18080)
- `docker-compose.gb10.yml` — the GB10 override: port 18080, the sentinel's
  operating posture, and (v1.2 Phase C) the read-only `field-manifests` and
  `field-keys` volumes with their one-shot writers `manifests-admin` and
  `keys-admin` (`tools/volume_admin.py`). The file's header has the one
  command for installing a manifest and for generating a key.
- Every image bakes `FIELD_BUILD_SHA` (a build arg; `unknown` when not given)
  and every `/health` reports it as `build_sha`. Build with
  `FIELD_BUILD_SHA=$(git rev-parse HEAD) docker compose ... build`.
- `fixtures/upgrade-smoke/` — CI's `compose-upgrade-smoke`: `make_fixture.py`
  writes an old-schema `/data` (pre-C2 single-file ledger, pre-v1.2 registry,
  manifests on `field-data`, rosters), `upgrade_flow.py` is the positive
  ALLOW flow the job runs through the proxy, `check_mount.py` asserts the
  read-only mounts inside each container. The job has not run on
  rog-command (no docker there); its non-docker half runs locally in
  `tools/tests/test_upgrade_smoke_fixture.py`.
