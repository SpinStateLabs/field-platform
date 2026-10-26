# claude-approver: its OWN image (compose service `approver`, profile `approver`).
# Deliberately NOT in integration/demo/Dockerfile or integration/fly/Dockerfile:
# this is the only image that installs the `anthropic` SDK, and the only one
# that will ever hold the Managed Agents org API key (as a read-only file
# mount, never baked in). Build context is the repo root:
#   FIELD_BUILD_SHA=$(git rev-parse HEAD) docker compose ... --profile approver build approver
FROM python:3.12-slim

WORKDIR /platform
COPY packages/field-core/ packages/field-core/
COPY services/claude-approver/ services/claude-approver/

# field-core first (claude-approver depends on it by name), then the service,
# which pulls anthropic>=2.3.0,<3 (+ httpx2), fastapi, uvicorn, typer, httpx from PyPI.
RUN pip install --no-cache-dir ./packages/field-core ./services/claude-approver

ENV FIELD_DATA_DIR=/data
VOLUME /data

# The SHA label passed as FIELD_BUILD_SHA at build time (NOT verified against
# the files built); /health reports it as build_sha (field_core.buildinfo).
# Declared LAST so a new SHA rebuilds only this layer. Same tail as
# integration/demo/Dockerfile.
ARG FIELD_BUILD_SHA=unknown
ENV FIELD_BUILD_SHA=${FIELD_BUILD_SHA}
