# Shared image for all FIELD Platform services.
# VERIFIED 2026-08-08 on GB10 (DGX Spark, aarch64, Docker 29 / Compose v5):
# build + up + governed smoke test PASS. x86_64 compose run still pending.
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
    ./services/kill-switch \
    ./services/conformance-sentinel \
    ./services/incident-replay \
    ./services/compliance-crosswalk \
    ./services/force-gateway \
    ./services/federation-broker \
    ./services/ops-console

ENV FIELD_DATA_DIR=/data
VOLUME /data
