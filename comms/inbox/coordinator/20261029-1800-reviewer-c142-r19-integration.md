# C-142 / R-19 reviewer report: integration/ compose, Caddy and entrypoint files (main 444e49b)

VERDICT: no service port beyond the proxy is published and no secret literal sits in an environment block. The images run as root with no hardening and are not reproducible; there are no compose healthchecks; the committed defaults leave the fail-open flags off, by design.

OBJECTIONS FIRST
1. A static read of descriptors says nothing about what a live estate runs; the live GB10 and Fly estates were not inspected.
2. Absence findings (no USER, no healthcheck) rest on grep and a YAML parse; a Dockerfile `RUN` that drops privileges in a way my grep missed is possible, so I also read the Dockerfile blocks.
3. I did not re-read every Caddyfile this round; the Caddy route and header findings are in C-48, C-91 and C-100.

ASSUMPTIONS
1. Main 444e49b; `integration/demo/docker-compose.yml` (15 services), `docker-compose.gb10.yml` (20), both Dockerfiles, `fly.toml`, `entrypoint.sh` (grep), parsed with PyYAML (a loader that tolerates the compose `!override` tag). [HIGH]

REASONING
1. Published ports (sound): only `proxy` publishes: demo `docker-compose.yml:152` `8080:8080`; GB10 `18080:8080` and `18443:8443` (compose header :11-17: phase 1 keeps 18080 as plain HTTP "all interfaces", phase 2 rebinds it to 127.0.0.1). No host IP on any mapping, so 0.0.0.0. This is F-C48-1/D-12 context, unchanged. Fly: `internal_port = 8080` (Caddy), `force_https = true` (fly.toml). [HIGH]
2. Secrets in environment blocks (sound): over both compose files, every variable whose name contains SECRET, KEY, TOKEN or PASSWORD is a file path (`FIELD_LEDGER_CALLER_KEY=/run/caller-key/<svc>.pem`, `FIELD_OPERATOR_KEY_FILE=/run/field/keys/...`, `CLAUDE_APPROVER_API_KEY_FILE=...`) or a `${VAR}` forward; 0 literals. `fly.toml` says the secret is set with `fly secrets set`, never in `[env]`; its only key-like value is a path, and a public-key fingerprint. [HIGH]
3. MEDIUM, F-C142-1: containers run as root with no hardening: neither Dockerfile (`integration/demo/Dockerfile`, `integration/fly/Dockerfile`) has a `USER`; neither entrypoint adds one (grep for USER/useradd/adduser/chown/nonroot: no hit); no compose service sets `user:`, `read_only`, `cap_drop` or `security_opt` (grep: only `network_mode: none` on three one-shot admin jobs, gb10 :204, :215, :224). Fifteen to twenty services holding the perimeter secret and key files run uid 0 with a writable root file system. [HIGH on the absence]
4. LOW, F-C142-2: no reproducible build: both Dockerfiles use `FROM python:3.12-slim` (demo :9, fly :18), `COPY --from=caddy:2-alpine` (fly :54) and compose `image: caddy:2-alpine` (:150): floating tags, no digests; `pip install --no-cache-dir ./packages/field-core ./services/...` resolves each package's dependency ranges at build time with no lock file or hashes, so a rebuild on another day can ship different fastapi/pydantic/cryptography. The GB10 and Fly deploys rebuild. [HIGH on the lines; the consequence is general]
5. LOW, F-C142-3: no `healthcheck:` on any compose service (0 hits in both compose files); readiness is established by CI shell loops and by `estate_probe`, not by the container runtime, so `docker compose ps` reports "running" for a service that is up but dead behind Caddy; `restart:` appears 3 times (base) and 5 times (GB10), most `restart: "no"` on one-shots. Fly has `[[http_service.checks]]` through Caddy (fly.toml, v1.2 X0). [HIGH on the absence]
6. Default-on risky flags (reported, by design): the committed compose files default every Phase G / signing / enforce flag to OFF: `FIELD_OPERATOR_REQUIRE=${...:-}`, `FIELD_LEDGER_REQUIRE_SIGNING=${...:-0}`, `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=${...:-0}`, `FORCE_GATEWAY_ENFORCE=${...:-0}`, `FORCE_GATEWAY_MOCK=${...:-}`, and `FIELD_SHARED_SECRET=${...:-}` (empty: demo mode; the topology lint covers the deployed topologies and its allowlist expires 2026-11-23, see C-143). A GB10 restart without its `.env` starts open on every one of these. [HIGH]
7. INFO, F-C142-4: `latest`-tag check: none; every `image:` is a pinned major (`caddy:2-alpine`); services are `build:`. [HIGH]

CONCLUSION
Add `USER` (and `read_only`/`cap_drop: [ALL]` where the services allow) to both Dockerfiles, pin base images by digest and install with a constraints file, and add compose healthchecks that call `/health`. Not done: live-estate inspection; a fresh Caddyfile pass.
