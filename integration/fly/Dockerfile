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
FROM python:3.12-slim

WORKDIR /platform
COPY packages/ packages/
COPY services/ services/

RUN pip install --no-cache-dir \
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

# Caddy is a static Go binary — runs on slim with no extra libs.
COPY --from=caddy:2-alpine /usr/bin/caddy /usr/bin/caddy
COPY integration/fly/Caddyfile /etc/caddy/Caddyfile
COPY integration/fly/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV FIELD_DATA_DIR=/data
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
