"""The Crosswalk's own FIELD manifest (ADR 07, mirroring the Sentinel S4
pattern). Founder & CTO is the named accountability owner (until a client CCO
formally owns their pack); the delegation scope is generation verbs only;
``enforcement.spend_cap`` is the gated-suggestion budget the governor meters:

    governor set-cap compliance-crosswalk --from-manifest <path>

This module only locates and loads the artifact — the Crosswalk ships no code
path that registers itself, signs a pack, or edits its own authority."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

SELF_AGENT_ID = "compliance-crosswalk"


def self_manifest_path() -> Path:
    return Path(str(files("compliance_crosswalk") / "self_manifest.yaml"))


def load_self_manifest() -> dict:
    import yaml

    return yaml.safe_load(self_manifest_path().read_text(encoding="utf-8"))
