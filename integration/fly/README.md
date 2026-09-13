# Fly.io sandbox estate — one container, one Machine

This directory packages the whole FIELD Platform as **one container** for a
single Fly.io Machine: the public **sandbox estate** behind the Force-Field
Portal. The thirteen served services (twelve governance systems + the
ops-console) bind `127.0.0.1` inside the container (the image installs
field-core plus all thirteen service packages); a Caddy
reverse proxy on `:8080` is the only externally reachable listener, with the
same path-prefix route map as the compose stack (`/registry`, `/ledger`,
`/delegation`, `/sentinel`, `/killswitch`, `/governor`, `/replay`, `/gateway`,
`/federation`, `/lifecycle`, `/attest`, `/crosswalk`, console at `/`).

Ground truth for service commands/ports is `integration/demo/docker-compose.yml`;
the pip install set mirrors `integration/demo/Dockerfile`. Keep them in sync.

This is the **PRODUCT estate — sentinel `enforce`**. It is NOT the GB10
burn-in estate (which runs `log_only` and is private). Do not confuse them.

## Prerequisites

- `flyctl` installed and authenticated: `fly auth login` — run by the human
  operator in a browser. Never paste org tokens into chats, files, or CI
  variables that end up in the repo.
- The repo checked out; all commands below run **from the repo root** (the
  Docker build context must contain `packages/` and `services/`).

## First deploy

```sh
# 1. Create the app (rename force-field-sandbox first if launching for real —
#    it is a placeholder in fly.toml).
fly apps create force-field-sandbox

# 2. Persistent volume for /data (FIELD_DATA_DIR) in the app's region.
fly volumes create ff_data --app force-field-sandbox --region yyz --size 1

# 3. Shared secret — generate a strong random value; this is what gates every
#    non-/health endpoint once set. Never commit it anywhere.
fly secrets set --app force-field-sandbox FIELD_SHARED_SECRET=<generated>

#    Optional: real upstream for the FORCE gateway. Without it, /gateway/health
#    works but POST /gateway/v1/messages returns 502 naming the missing key.
# fly secrets set --app force-field-sandbox ANTHROPIC_API_KEY=<key>

# 4. Deploy — from the REPO ROOT, context "." so packages/ and services/ are
#    in the build context; --dockerfile is relative to that context. From a
#    CLEAN worktree: FIELD_BUILD_SHA is a label nothing checks against the
#    files being built.
fly deploy . -c integration/fly/fly.toml --dockerfile integration/fly/Dockerfile \
  --build-arg FIELD_BUILD_SHA=$(git rev-parse HEAD)
```

Smoke it: `curl https://<app>.fly.dev/health` (console, proxy root) and
`curl https://<app>.fly.dev/registry/health` … for each prefix. Every
`/health` reports `build_sha` (v1.2 Phase C): the SHA passed with
`--build-arg`, or `unknown` without it. The gate checks all prefixes at once
with `python3 tools/estate_probe.py --base http://127.0.0.1:8080 health
--expect-build-sha <SHA>` inside the machine.

## Manifests and keys on Fly — one volume

The GB10 keeps manifests and signing keys on their own named volumes, mounted
read-only into the services that read them and written only by one-shot admin
containers (`integration/demo/docker-compose.gb10.yml`). **Fly keeps its
single volume**: manifests stay at `/data/manifests` and keys at `/data/keys`
on `ff_data`. The same writer tool ships in the image, so an anchor key is
generated in-machine without key material crossing the session:

```sh
fly ssh console --app force-field-sandbox \
  -C "python /platform/tools/volume_admin.py keys generate --dir /data/keys ledger-anchor"
```

It writes `ledger-anchor.pem` (0600, umask 077, never overwriting) and
`ledger-anchor.pub.pem`, and prints only the paths and the public key's
fingerprint. On Fly nothing enforces who may write either directory (next row).

Keep the PUBLIC key off-box as well (A4): rotation anchors and archived-segment
sidecars verify only with the PEM, never with the fingerprint. `export-public`
prints the public key and nothing else, after checking that the file is an
Ed25519 public key:

```sh
fly ssh console --app force-field-sandbox \
  -C "python /platform/tools/volume_admin.py keys export-public --dir /data/keys ledger-anchor" \
  | tr -d '\r' | sed -n '/-----BEGIN PUBLIC KEY-----/,/-----END PUBLIC KEY-----/p' > ledger-anchor-fly.pub.pem
openssl pkey -pubin -in ledger-anchor-fly.pub.pem -outform DER | tail -c 32 | sha256sum   # == the fingerprint
```

## Attach to the portal

In the Netlify site settings for the Force-Field Portal set:

- `ESTATE_URL` = `https://<app>.fly.dev`
- `ESTATE_SHARED_SECRET` = the same value given to `fly secrets set
  FIELD_SHARED_SECRET=...` above (the portal sends it as `x-field-auth`).

## The estate model

- This Machine is the **shared sandbox estate for the free tier**: every
  free-tier portal user lands on the same estate.
- **Paid tiers get a dedicated Machine each** — clone this pattern (new Fly
  app, new volume, new secret, same image), one estate per customer.

## LIMITS

- **Single machine, single writer — by design.** The ledger and every other
  service assume one writer on one volume. Do not scale this app to more
  than one Machine (`min_machines_running = 1`, `auto_stop_machines = "off"`).
- **Sandbox data may be wiped at any time.** No durability promise is made to
  free-tier users. There is **no auto-wipe scheduled yet** — wiping is a
  manual operation today.
- **Ledger retention (C2) is served-only here.** The machine's supervisor
  (`wait -n`) cannot run with the ledger stopped, so `ledger rotate`, `ledger
  hold` and `ledger retention apply` go through `/ledger/*` routes, never
  `--offline`. `FIELD_LEDGER_ANCHOR_KEY` is unset until arming step A4 places
  the key under `/data`, so `/ledger/rotate` answers 503 until then.
  `FIELD_LEDGER_RETENTION_DAYS` is `2555`. Archived segments stay on the same
  `/data` volume (archival renames; it frees no space).
- **(b) Manifests and signing keys are writable by every service process.**
  Declared, and a true limit, not an unbuilt feature. On the GB10 a FILE in
  the `field-manifests` volume (every service's `/data/manifests`) or the
  `field-keys` volume (the ledger's `/data/keys`) can only be changed by the
  one-shot admin containers, because each service is its own container with
  those read-only mounts — the other twelve containers have no `field-keys`
  mount, so their `/data/keys` is a writable directory on `field-data` that the
  ledger never reads (and even there `manifest_ref` is not confined to that directory: a
  manifest elsewhere on the read-write `/data` is honoured if an agent's ref
  points at it). Here the thirteen
  services and Caddy are one container running as one user (root) on one
  volume. A per-service read-only mount cannot exist inside one container,
  and a Fly Machine mounts a single volume. Any code execution in any
  service can therefore rewrite `/data/manifests` (changing an agent's
  envelope, which every reader honours on its next mtime check) or read and
  replace `/data/keys`. Nothing on this estate records which manifest bytes a
  verdict was reached under. It would stop being (b) only if
  this estate were split into one Machine per service; no plan item does
  that (D7's second Fly app is for a canary process, not the services).
- **Sentinel runs `enforce`.** Ungoverned actions are blocked, not just
  logged — this is the product behavior, demonstrated on purpose.
- **TLS terminates at the Fly edge** (`force_https`); Caddy speaks plain HTTP
  on the internal port. Nothing else in the container listens externally.
- **The portal is the only intended caller** once `FIELD_SHARED_SECRET` is
  set: every endpoint except `/health` requires the `x-field-auth` header.
