# FIELD Platform — single-container image for the Fly.io sandbox estate.
#
# One container = the whole estate: the thirteen served services (twelve
# governance systems + ops-console) bind 127.0.0.1 — field-core plus all
# thirteen service packages are installed — and a Caddy reverse proxy (static
# Go binary copied from the official image) is the only 0.0.0.0 listener, on
# :8080. Route map: integration/fly/Caddyfile.
# Supervisor: integration/fly/entrypoint.sh (any child dying takes the
# machine down non-zero so Fly restarts it).
#
# BUILD CONTEXT IS THE REPO ROOT (packages/ and services/ live there):
#   docker build -f integration/fly/Dockerfile -t ff-fly-estate .
#
# KEEP IN SYNC: the COPY + pip install block below mirrors
# integration/demo/Dockerfile (the compose ground truth). If a service is
# added or removed there, change it here too. Order: lifecycle-manager and
# attestation-reporter follow spend-governor (v1.2 B4 relies on that).
# Base image pinned by digest (C-152): the index digest of python:3.12-slim read from
# Docker Hub on 2026-10-28 (multi-arch). Refresh on purpose, with a compose-smoke run.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

WORKDIR /platform
COPY packages/ packages/
COPY services/ services/
COPY integration/constraints.txt integration/constraints.txt

RUN pip install --no-cache-dir -c integration/constraints.txt \
    ./packages/field-core \
    ./services/sealed-ledger \
    ./services/agent-registry \
    ./services/delegation-authority \
    ./services/spend-governor \
    ./services/lifecycle-manager \
    ./services/attestation-reporter \
    ./services/kill-switch \
    ./services/conformance-sentinel \
    ./services/incident-replay \
    ./services/compliance-crosswalk \
    ./services/force-gateway \
    ./services/federation-broker \
    ./services/ops-console

# Volume admin (v1.2 Phase C), mirrored from integration/demo/Dockerfile. On
# Fly there is no separate manifests or keys volume (a Machine mounts one
# volume), so only `keys generate --dir /data/keys` is useful here.
COPY tools/volume_admin.py tools/volume_admin.py

# The deploy gate's evidence engine (docs/runbooks/v1.2-deploy-rollback.md
# section 5): the smoke machine and the deployed machine both run
#   python3 /platform/tools/estate_probe.py --base http://127.0.0.1:8080 ...
# over `fly ssh console`. Standard library only, so no pip line. Fly only: the
# GB10 runs it from the host checkout, so integration/demo/Dockerfile does not
# carry it. Missing until 2026-10-05, which stopped that day's deploy at smoke.
COPY tools/estate_probe.py tools/estate_probe.py

# Caddy is a static Go binary — runs on slim with no extra libs.
# caddy:2-alpine pinned by index digest (C-152), read 2026-10-28.
COPY --from=caddy:2-alpine@sha256:eb4d35b7452d1ab6171fbdbe8d9275b2301dad6dad92115d91e19fb9b24d510f /usr/bin/caddy /usr/bin/caddy
COPY integration/fly/Caddyfile /etc/caddy/Caddyfile
COPY integration/fly/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# G1 F3/F4 (field-platform issues 1067, 1068): ff-harden (write + read back the four sysctls the entrypoint sets when
# FIELD_HARDEN_SYSCTLS=1; default off), and no setuid/setgid files in the image. The G1 battery found su, mount, umount,
# passwd, chfn, chsh, gpasswd, newgrp (setuid root) and chage, expiry, unix_chkpwd (setgid) from the python:3.12-slim
# base; every estate process already runs as root, so none of them is needed. Keep this block AFTER every COPY/RUN that
# can add a binary; the `test -z` fails the build if any setuid/setgid file is left. tools/topology_lint.py admits
# exactly these two find/test commands (_RUN_PIECE_OK).
COPY tools/ff-harden.sh /usr/local/sbin/ff-harden
RUN chmod 0755 /usr/local/sbin/ff-harden \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
 && test -z "$(find / -xdev -type f -perm /6000)"

ENV FIELD_DATA_DIR=/data
EXPOSE 8080

# The SHA label passed as FIELD_BUILD_SHA at build time (NOT verified against
# the files built); every service's /health reports it as build_sha
# (field_core.buildinfo). Declared LAST so a new SHA rebuilds
# only this layer. Pass it on deploy (see fly.toml):
#   fly deploy . -c integration/fly/fly.toml --dockerfile integration/fly/Dockerfile \
#     --build-arg FIELD_BUILD_SHA=$(git rev-parse HEAD)
# The entrypoint's children inherit it. Unset => "unknown".
ARG FIELD_BUILD_SHA=unknown
ENV FIELD_BUILD_SHA=${FIELD_BUILD_SHA}
ENTRYPOINT ["/entrypoint.sh"]
