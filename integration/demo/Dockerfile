# Shared image for all FIELD Platform services.
# VERIFIED 2026-08-08 on GB10 (DGX Spark, aarch64, Docker 29 / Compose v5):
# build + up + governed smoke test PASS. x86_64 compose run still pending.
#
# Installs field-core plus all thirteen service packages (twelve governance
# systems + ops-console). KEEP IN SYNC with integration/fly/Dockerfile.
# Order: lifecycle-manager and attestation-reporter follow spend-governor
# (v1.2 B4 relies on that ordering).
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
    ./services/ops-console \
    ./packages/field-agent

# packages/field-agent (the client SDK) is here for v1.2 X3: the GB10
# `canary-agent` compose service runs `python -m field_agent.canary serve`, and
# the X3 live check runs `python -m field_agent.canary x3-check` inside the
# kill-switch container. It serves nothing in any platform service. The one
# deliberate divergence from integration/fly/Dockerfile's KEEP IN SYNC: Fly has
# no canary process until D7, so its image does not install it.

# One-shot volume admin (v1.2 Phase C): seeds and installs manifests into the
# GB10 field-manifests volume and generates keys into field-keys
# (docker-compose.gb10.yml manifests-admin / keys-admin). Stdlib + field-core.
COPY tools/volume_admin.py tools/volume_admin.py

ENV FIELD_DATA_DIR=/data
VOLUME /data

# The SHA label passed as FIELD_BUILD_SHA at build time (NOT verified against
# the files built); every service's /health reports it as build_sha
# (field_core.buildinfo). Declared LAST so a new SHA rebuilds
# only this layer, never the pip install above. compose passes it as a build
# arg from the host environment:
#   FIELD_BUILD_SHA=$(git rev-parse HEAD) docker compose ... build
# Unset => "unknown", which `estate_probe.py health --expect-build-sha` fails.
ARG FIELD_BUILD_SHA=unknown
ENV FIELD_BUILD_SHA=${FIELD_BUILD_SHA}
