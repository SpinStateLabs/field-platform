# Fly redeploy to current main: checklist (Stage 4a, then 4b)

Status: plan only (C-1164, WP7). Nothing here has been run. It restates `v1.2-deploy-rollback.md` sections 5, 6 and
the Phase G "Arming, Fly" block as one ordered list; where the two disagree, the runbook wins. No deploy, token,
expiry or flag value appears in this file: every `<...>` is read from the estate when the step runs.

**DON-ONLY** marks a step only Don runs or only Don's go sentence releases. Everything else may be run by a builder
or verifier on Don's instruction, never on its own initiative. Each step is behind its own go sentence (runbook
section 7, "Arming, Fly").

Not in the sources I read (so not decided here): the soak floors Don ruled, the deploy SHA, the label, the machine
memory size, the volume id. Fill them in at run time; do not guess them.

## Stage 4a: redeploy the current-main image, then arm LOG-ONLY

### Before anything (record)
- [ ] **DON-ONLY** Name the deploy SHA (full 40 hex) and confirm CI is green on it. The checklist is void if main
      moves after the SHA is named: re-name it.
- [ ] Record the pins (runbook section 1): `fly releases --image` for the current release image ref, the Fly ledger
      `event_count` and head (read through the estate, not from STATE.md), and `fly volumes list -a force-field-sandbox`
      showing exactly one `ff_data` volume attached to the one machine.
- [ ] Save the pre-deploy `fly.toml` (rollback F-R1 needs it).

### Prove the image (section 5, step 1; the public machine is untouched)
- [ ] Clean worktree at the deploy SHA. Build only and push with an image label and
      `--build-arg FIELD_BUILD_SHA=$(git rev-parse HEAD)`. Without the build arg every `/health` reports `unknown`.
- [ ] Start a service-less smoke machine from that exact image (no `--port`, no volume). Run `estate_probe.py health
      --expect-build-sha <deploy SHA>` inside it, read VmRSS, destroy the machine.
- [ ] Image carries `integration/fly/entrypoint.sh` with the per-process identities (C-5), or the Phase G arming below
      does not apply. Check with `tools/fly_identity_check.py --expect none` inside the smoke machine.

### Snapshot (section 5, step 2)
- [ ] `fly volumes snapshots create` on the confirmed `ff_data` volume. Record the snapshot id. Snapshots are kept 5
      days by default; extending retention is a cost call: **DON-ONLY**.

### Deploy (section 5, step 3)
- [ ] **DON-ONLY** go sentence for the deploy. Then deploy exactly the smoked image with
      `fly deploy -c integration/fly/fly.toml --image registry.fly.io/force-field-sandbox:<label> --ha=false -a force-field-sandbox`.
      The http service checks make the deploy wait on health.

### Verify (section 5, step 4)
- [ ] Exactly one machine, on the confirmed volume, running the new image ref.
- [ ] In-machine: `estate_probe.py health --expect-perimeter --expect-build-sha <deploy SHA>`, `continuity`, and the
      canary catalogue on `canary-fly`.
- [ ] Record: SHA, CI status and who confirmed it, pins before and after, release and snapshot ids.

### Arm LOG-ONLY (Phase G, "Arming, Fly" steps 1 and 3)
Precondition: `fly.toml` `[env]` does NOT carry the operator variables, and the image is the one just verified.
- [ ] Build `operators.json` on Don's own machine with `tools/operator_keygen.py`, then `--check` it (exit 0).
      **DON-ONLY** (the key is printed once; no session sees it).
- [ ] Place it by temp file and `mv -f` inside `/data/operators/` (never write the live file in place), mode 0600.
- [ ] **DON-ONLY** go sentence for arming. Import the four per-daemon identity secrets together with the registry
      path through `fly secrets import` on stdin (never argv). One restart.
- [ ] `fly_identity_check.py --expect four` inside the machine (names, counts, modes only).
- [ ] `phase_g_check --base https://force-field-sandbox.fly.dev --agent canary-fly --expect-mode log-only` with Don's
      key FILE.
- [ ] Open item before Stage 3 (not Stage 4): `registry_edit` versus self-agent re-provisioning (runbook, "OPEN ITEM").
      I do not know whether it is resolved; read the current runbook text.

### Stage 4a rollback
- [ ] Image only: `fly deploy -c <saved fly.toml> --image <recorded previous ref> --ha=false` (F-R1), and only to a
      Phase C or later image. Below Phase C Fly is fix-forward only (section 6).
- [ ] Data: F-R2 (snapshot to a new volume, machine stopped). Never tested on this app. **DON-ONLY**.
- [ ] Arming only: `fly secrets unset FIELD_OPERATOR_REGISTRY`. The file and identity secrets may stay.

## Stage 4b: REQUIRE

Gate: Stage 4a verified and held, and Don's own go sentence. The soak floor before 4b is not in the sources I read.

- [ ] **DON-ONLY** Every internal caller has its `FIELD_OPERATOR` identity first (runbook "REQUIRE-readiness"); a
      caller without one is refused once REQUIRE is set.
- [ ] **DON-ONLY** Set the REQUIRE flag through `fly secrets import` on stdin.
- [ ] Verify with `phase_g_check ... --expect-mode enforce` and Don's key FILE.
- [ ] Record the date, release, and the check output in the deploy record.

### Stage 4b rollback (order matters)
- [ ] `fly secrets unset FIELD_OPERATOR_REQUIRE` FIRST, then `fly secrets unset FIELD_OPERATOR_REGISTRY`.
- [ ] Never roll back by image alone once REQUIRE has been set: an image without C-5 would present no identity and
      break every kill, and ledger rows already carry authenticated-operator fields permanently.

## Caveat that applies to both

Single container: every process can read `/data/operators/operators.json` and every key file, so the protection is
against callers, not against code inside the machine (runbook, the Fly (b) row).
