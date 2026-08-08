# Shared image for all FIELD Platform services.
# ⚠ UNTESTED: docker is not installed on the primary build machine
# (STATE.md OQ-5). run_demo.sh (local processes) is the verified path.
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
    ./services/force-gateway

ENV FIELD_DATA_DIR=/data
VOLUME /data
