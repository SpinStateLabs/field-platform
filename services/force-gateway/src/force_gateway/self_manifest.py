"""The Gateway's own FIELD manifest (ADR 10, mirroring the Sentinel S4
pattern). Founder & CTO is the named accountability owner; the delegation
scope is observer verbs only; ``enforcement.spend_cap`` is the sampled
hygiene-judge budget the governor meters:

    governor set-cap force-gateway --from-manifest <path>

This module only locates and loads the artifact — the Gateway ships no code
path that registers itself or sets its own cap (it must not be able to grant
itself authority)."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

SELF_AGENT_ID = "force-gateway"


def self_manifest_path() -> Path:
    return Path(str(files("force_gateway") / "self_manifest.yaml"))


def load_self_manifest() -> dict:
    import yaml

    return yaml.safe_load(self_manifest_path().read_text(encoding="utf-8"))
