"""Access to the four shipped manifest templates, vendored verbatim."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

TEMPLATE_NAMES = ("default", "financial-agent", "read-only-agent", "client-facing-agent")


def _template_path(name: str) -> Path:
    if name not in TEMPLATE_NAMES:
        raise KeyError(
            f"unknown template {name!r}; choose from {', '.join(TEMPLATE_NAMES)}"
        )
    root = resources.files("field_core") / "templates"
    return Path(str(root / f"field-manifest-{name}.yaml"))


def template_text(name: str) -> str:
    return _template_path(name).read_text(encoding="utf-8")


def template_data(name: str) -> dict[str, Any]:
    data = yaml.safe_load(template_text(name))
    assert isinstance(data, dict)
    return data


def schema_json() -> str:
    root = resources.files("field_core") / "schema"
    return Path(str(root / "manifest-schema.json")).read_text(encoding="utf-8")
