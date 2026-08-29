"""The Sentinel's own FIELD manifest (ADR 02 S4) — who guards the guard.

The committed ``self_manifest.yaml`` names the Founder & CTO as the
accountability owner, restricts the Sentinel's delegation scope to
read/evaluate/append/invoke (read-only grounding), and declares the
semantic-judge budget as ``enforcement.spend_cap`` — the governor meters
against it via the existing flow:

    governor set-cap conformance-sentinel --from-manifest <path>

This module only locates and loads the artifact. Registration and cap
application deliberately stay with the operator-side tools (registry CLI +
``governor set-cap``): the Sentinel must not be able to grant itself
authority, so it ships no code path that writes its own governance state.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

SELF_AGENT_ID = "conformance-sentinel"


def self_manifest_path() -> Path:
    return Path(str(files("conformance_sentinel") / "self_manifest.yaml"))


def load_self_manifest() -> dict:
    import yaml

    return yaml.safe_load(self_manifest_path().read_text(encoding="utf-8"))
