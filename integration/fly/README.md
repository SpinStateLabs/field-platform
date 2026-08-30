# Fly.io sandbox estate — one container, one Machine

This directory packages the whole FIELD Platform as **one container** for a
single Fly.io Machine: the public **sandbox estate** behind the Force-Field
Portal. The ten served services bind `127.0.0.1` inside the container (the
image installs all eleven packages — compliance-crosswalk stays CLI-only,
uncomposed by design); a Caddy
reverse proxy on `:8080` is the only externally reachable listener, with the
same path-prefix route map as the compose stack (`/registry`, `/ledger`,
`/delegation`, `/sentinel`, `/killswitch`, `/governor`, `/replay`, `/gateway`,
`/federation`, console at `/`).

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
fly volumes create ff_data --app force-field-sandbox --region yul --size 1

# 3. Shared secret — generate a strong random value; this is what gates every
#    non-/health endpoint once set. Never commit it anywhere.
fly secrets set --app force-field-sandbox FIELD_SHARED_SECRET=<generated>

#    Optional: real upstream for the FORCE gateway. Without it, /gateway/health
#    works but POST /gateway/v1/messages returns 502 naming the missing key.
# fly secrets set --app force-field-sandbox ANTHROPIC_API_KEY=<key>

# 4. Deploy — from the REPO ROOT, context "." so packages/ and services/ are
#    in the build context; --dockerfile is relative to that context.
fly deploy . -c integration/fly/fly.toml --dockerfile integration/fly/Dockerfile
```

Smoke it: `curl https://<app>.fly.dev/health` (console, proxy root) and
`curl https://<app>.fly.dev/registry/health` … for each prefix.

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
- **Sentinel runs `enforce`.** Ungoverned actions are blocked, not just
  logged — this is the product behavior, demonstrated on purpose.
- **TLS terminates at the Fly edge** (`force_https`); Caddy speaks plain HTTP
  on the internal port. Nothing else in the container listens externally.
- **The portal is the only intended caller** once `FIELD_SHARED_SECRET` is
  set: every endpoint except `/health` requires the `x-field-auth` header.
