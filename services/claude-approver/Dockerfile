# claude-approver: its OWN image (compose service `approver`, profile `approver`).
# Deliberately NOT in integration/demo/Dockerfile or integration/fly/Dockerfile:
# this is the only image that installs the `anthropic` SDK, and the only one
# that will ever hold the Managed Agents org API key (as a read-only file
# mount, never baked in). Build context is the repo root:
#   FIELD_BUILD_SHA=$(git rev-parse HEAD) docker compose ... --profile approver build approver
# Base image pinned by digest (C-152): the index digest of python:3.12-slim read from
# Docker Hub on 2026-10-28 (multi-arch). Refresh on purpose, with a compose-smoke run.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

WORKDIR /platform
COPY integration/constraints.txt integration/constraints.txt
COPY packages/field-core/ packages/field-core/
COPY services/claude-approver/ services/claude-approver/

# field-core first (claude-approver depends on it by name), then the service,
# which pulls anthropic>=2.3.0,<3 (+ httpx2), fastapi, uvicorn, typer, httpx from PyPI.
# Constrained like the other images (C-323, reviewer C-263 F-C263-1): this is the image that
# holds the org API key, so its whole dependency closure is pinned in integration/constraints.txt.
RUN pip install --no-cache-dir -c integration/constraints.txt \
    ./packages/field-core ./services/claude-approver

ENV FIELD_DATA_DIR=/data
VOLUME /data

# The SHA label passed as FIELD_BUILD_SHA at build time (NOT verified against
# the files built); /health reports it as build_sha (field_core.buildinfo).
# Declared LAST so a new SHA rebuilds only this layer. Same tail as
# integration/demo/Dockerfile.
ARG FIELD_BUILD_SHA=unknown
ENV FIELD_BUILD_SHA=${FIELD_BUILD_SHA}
