"""deployment_agent - SKELETON of the FIELD-governed deployment agent (ADR-0079).

Pure, deterministic code: standard library plus PyYAML, no network call, no
real provider, no signature cryptography. See tools/deployment_agent/README.md
for what exists, what does not, and the placeholders.

Design source (harness repo, branch rebaseline-2026-10): adr/ADR-0079-*.md and
docs/proposals/03-autonomous-cicd-and-key-management.md. Nothing here holds,
reads or prints a secret; credentials are referenced by id or 8-character
prefix only.
"""
from __future__ import annotations

VERSION = "0.1.0-skeleton"
AGENT_NAME = "ssl-deployment-agent"  # name is an ADR-0079 proposal
