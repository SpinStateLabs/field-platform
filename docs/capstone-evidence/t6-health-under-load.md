# T6 — does one heavy request make every /health fail? (Linux track, 2026-11-20)

**Result: partly reproduced.** Every /health slowed down together, and the ledger's /health hit the 5 s timeout
once. The sustained, all-service failure seen on the Fly estate was **not** reproduced.
No code fix ships with this note: no candidate passed a test that fails on main.

Production finding (Fly estate, image main-6bc2c80): during one heavy authenticated request (/attest/pack,
/ledger/verify or an unfiltered /ledger/events; about 11,200 events, 5.7 MB) all eight monitored /health answers
failed for 11-63 s. The monitor uses a 5 s timeout; two failed polls in a row roll back.

> **Correction 2026-11-21 (VM size).** This record's "1 CPU" rows and its "Fly VM size" label are local Docker runs
> sized to the Fly VM as configured on 2026-11-20 (one shared CPU); only the "Production finding" paragraph comes from
> the estate. The measurements are unchanged. The configured
> size has since changed: `integration/fly/fly.toml` `[[vm]]` now sets `cpus = 4` (shared, 2gb; pinned by
> `tools/tests/test_fly_vm_size.py`). No row here was re-measured at 4 CPUs, so the table says nothing about the
> 4-CPU configuration, and whether the running Machine has that size is not verified here.

## Method

- Stack: the Fly single-container image (`integration/fly/Dockerfile`, built as CI's fly-image-smoke job
  builds it) at main ba861753. That is thirteen CPython services plus Caddy in one container, the same
  layout as production.
- Data: 11,200 events appended through `POST /ledger/events` (the ledger's own append path and hash chain;
  7.3 MB on disk). The shared secret is a test value.
- Harness: `tools/health_under_load.py`. It polls every prefix's /health once a second with a 5 s timeout, one
  thread per prefix, around ONE heavy GET. It also reads the per-process CPU spent during that request from
  `/proc/<pid>/stat`.
- CPU limits: Docker CFS quota. Fly's shared vCPU is capped by Linux CFS bandwidth at 6.25% (5 ms per 80 ms) once
  its burst balance is spent ([Fly docs, CPU performance](https://fly.io/docs/machines/cpu-performance/)).
  `--cpus 0.0625` (6.25 ms per 100 ms) is the closest local equivalent.

## Results (committed harness, all 13 prefixes polled)

| config | heavy GET | HTTP | wall s | ledger CPU ms | attest CPU ms | /health polls during | failed (>=5 s / non-200) | idle max s (before) | ledger /health max s | max of the other 12 s |
|---|---|---|---|---|---|---|---|---|---|---|
| unlimited (4 host cores) | /attest/pack | 200 | 2.64 | 2560 | 80 | 26 | 0 | 0.036 | 0.103 | 0.015 |
| unlimited (4 host cores) | /ledger/verify | 200 | 0.31 | 310 | - | 0 | 0 | 0.013 | - | - |
| unlimited (4 host cores) | /ledger/events | 200 | 0.16 | 160 | - | 0 | 0 | 0.01 | - | - |
| 1 CPU, 2 GB (Fly VM size, full burst) | /attest/pack | 200 | 2.83 | 2590 | 70 | 39 | 0 | 0.076 | 0.075 | 0.009 |
| 1 CPU, 2 GB (Fly VM size, full burst) | /ledger/verify | 200 | 0.29 | 280 | - | 0 | 0 | 0.016 | - | - |
| 1 CPU, 2 GB (Fly VM size, full burst) | /ledger/events | 200 | 0.17 | 180 | - | 0 | 0 | 0.011 | - | - |
| 1/16 CPU, 2 GB (Fly baseline, balance spent) | /attest/pack | 200 | 16.9 | 300 | 110 | 202 | 1 | 3.412 | 5.003 | 1.798 |
| 1/16 CPU, 2 GB (Fly baseline, balance spent) | /ledger/verify | 200 | 25.6 | 500 | 120 | 311 | 0 | 1.601 | 2.499 | 1.997 |
| 1/16 CPU, 2 GB (Fly baseline, balance spent) | /ledger/events | 200 | 18.7 | 390 | 90 | 228 | 0 | 1.476 | 3.099 | 2.102 |
| 1/16 CPU + read lane at nice 19 (experiment, not shipped) | /attest/pack | 200 | 16.54 | n/a | n/a | 187 | 0 | 4.042 | 3.7 | 2.203 |
| 1/16 CPU + read lane at nice 19 (experiment, not shipped) | /ledger/verify | 200 | 26.71 | n/a | n/a | 329 | 0 | 0.811 | 4.099 | 2.101 |
| 1/16 CPU + read lane at nice 19 (experiment, not shipped) | /ledger/events | 200 | 17.11 | n/a | n/a | 206 | 0 | 1.109 | 3.715 | 2.203 |

Other configurations measured with the same polling logic (scratch version of the harness). None had a failed poll:

| configuration | heavy routes: wall time | worst /health |
|---|---|---|
| 1/4 CPU | pack 13.9 s, verify 1.4 s, events 0.8 s | 0.34 s |
| 1/16 CPU, 8 prefixes | events 10.2 s, verify 17.0 s, pack 105 s | ledger 2.3 / 2.6 / 3.8 s; others 1.7 s |
| 1/16 CPU at a 1 s CFS period | events 5.9 s, verify 7.9 s | ledger 2.0 s, others 0.9 s |
| 1 CPU, 1 GB | — | ledger 0.13 s |
| 1 CPU, 768 MB | — | ledger 0.14 s; peak 640 MiB, zero major page faults |

No Docker, one pinned core, no quota, back-to-back heavy reads: the ledger's /health stayed at or under 42 ms,
and the delegation service's at or under 11 ms.

Steady-state CPU of the container, 60 s windows, 1 CPU limit:

| load | % of one core |
|---|---|
| idle | 2.0% |
| 8 × 1 Hz /health polls | 3.9% |
| 13 × 1 Hz /health polls | 5.0% |

The Fly baseline is 6.25%.

## What the evidence supports

1. **No lock, no blocked event loop, no single worker.**
   - The ledger serves /health on its own lane (`sealed_ledger.api.create_app`, `app.state.lanes`), and
     `LedgerStore.health_info` never takes the read gate.
   - The other services' /health handlers read local state only; none calls the ledger.
   - Measured: the ledger's /health stayed at or under 42 ms on one pinned core during continuous heavy reads.
2. **The CPU is spent in the ledger process.**
   - One /attest/pack costs 2.56 s of ledger CPU and 0.08 s of attest CPU. It issues 16 `GET /events`
     (`PackEngine._event_count`, `_sweep_rows`, `_gate_verification_row`) and one `GET /verify`.
   - Each of those is a full-chain parse (`LedgerStore.events` / `verify` -> `_take_snapshot`).
3. **Production's durations fit a machine running at the Fly baseline.**
   - On this host, at Fly's baseline quota, the heavy routes take 10-26 s and /attest/pack takes 17-105 s,
     against 0.2-2.8 s at full speed.
   - Production's 11-63 s fits the baseline regime, not the burst regime. Production's CPU speed is unknown,
     so this rests on timing only.
4. **At the baseline, every /health slows together; the ledger's is the slowest.**
   - All services' /health slowed at once (other services up to 2.2 s). The ledger's reached 5.0 s; its
     /health shares a GIL with the read lane.
   - Before any heavy request, /health maxima were already 0.8-4.0 s. The resting estate plus 1 Hz polling
     takes most of the 6.25% quota (table above).
   - The heavy request is the marginal load that pushes demand over the quota.
5. **Under that load /attest/pack degrades silently.**
   - At 1/16 CPU with the pollers running, it answered HTTP 200 in 12.8 s with 19 of 26 metrics
     `unavailable` ("ledger unreachable").
   - The cause: attest's 10 s httpx timeout to the ledger (`attestation_reporter.api.engine_from_env`) expired.

## Not verified

- The Fly microVM is throttled as a whole: guest kernel, network stack and Caddy all sit inside the quota.
  Docker throttles only the container's processes; this host's TCP stack and docker-proxy were not throttled.
- Fly proxy behaviour when the `/ledger/health` http_service check (5 s timeout, 30 s interval) fails. Whether
  it stops routing every path would explain "all services at once", but this cannot be tested locally.
- Production's real traffic, ledger signing (F2) and caller keyring cost, the monitor's own implementation and
  path, and Fly's per-core speed.

## Estate measurements that would settle it (for the controller; this track sent nothing to any estate)

1. Fly metrics `cpu_balance` and `cpu_throttle` around the 2026-11-20 heavy requests. A balance near zero with
   throttling during the window means in-VM CPU starvation.
2. Inside the machine (`fly ssh console`), poll `http://127.0.0.1:8080/<prefix>/health` while the external
   monitor polls through the edge.
   - Inside fast, outside failing: the cause is the edge or proxy.
   - Both failing: the cause is in the VM.
3. The http_service check history for `/ledger/health` during the same windows.

## Options considered and not shipped

- **Lower the OS priority of the ledger's read lane (nice 19 on its threads).** Measured at 1/16 CPU: no
  improvement (table). The resting load already takes most of the quota, so priority cannot add headroom.
- **Move computation off the event loop.** Already done. The ledger runs heavy reads and their JSON
  serialisation in the read lane, and /attest/pack is a sync route on Starlette's threadpool. Nothing heavy
  is left on an event loop.
- **Cache keyed on the ledger head for /verify and the parsed snapshot.** This is the largest lever measured:
  /attest/pack costs 17 full-chain passes and could cost 1, about 6x less ledger CPU. Not shipped for three
  reasons:
  - the hit rate depends on the estate's append rate during a pack, which is unknown;
  - a parsed snapshot held in memory peaks at 0.3-0.4 GB at 100k events (`read_concurrency` docstring), on a
    2 GB machine;
  - no deterministic test of /health latency can fail on main without a CPU quota, which CI does not have.
- **Compute every pack metric from one `/events` fetch in attest.** Rejected: it changes each metric's printed
  `source_query`, so /attest/pack's output changes.
- **Run heavy reads in a low-priority child process.** This removes the shared GIL from the ledger's /health.
  Not shipped: the store must be re-opened in the child (signing and caller config), it costs an extra
  interpreter's memory, and it was not measured.
- **Deploy-side changes** (shared-cpu-2x / performance CPU, a lower monitor poll rate). Out of scope here
  (deploy configuration). They are the only measured lever that adds quota.
