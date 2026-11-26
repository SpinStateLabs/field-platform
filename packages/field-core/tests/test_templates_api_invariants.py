"""Invariants of field_core.templates_api (card S11-7): name-to-file bijection,
byte-exact text, and refusal of every name outside TEMPLATE_NAMES."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from field_core import templates_api
from field_core.manifest import SCHEMA_VERSION
from field_core.templates_api import (
    TEMPLATE_NAMES,
    _template_path,
    schema_json,
    template_data,
    template_text,
)

TEMPLATES_DIR = Path(templates_api.__file__).parent / "templates"
BAD_NAMES = [
    "",
    "default ",
    "DEFAULT",
    "../default",
    "../../pyproject",
    "default.yaml",
    "field-manifest-default.yaml",
    "nonexistent",
]


def test_shipped_files_match_template_names_exactly():
    on_disk = {p.name for p in TEMPLATES_DIR.glob("field-manifest-*.yaml")}
    assert on_disk == {f"field-manifest-{n}.yaml" for n in TEMPLATE_NAMES}


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
def test_template_text_is_file_bytes_and_data_has_schema_version(name):
    f = TEMPLATES_DIR / f"field-manifest-{name}.yaml"
    # read_text translates CRLF checkouts to LF: compare content, not EOL style
    assert template_text(name) == f.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert _template_path(name) == f
    data = template_data(name)
    assert isinstance(data, dict)
    assert data["schema_version"] == SCHEMA_VERSION


@pytest.mark.parametrize("fn", [_template_path, template_text])
@pytest.mark.parametrize("bad", BAD_NAMES + [None, 0, b"default"])
def test_unknown_names_refused_without_reading_any_file(fn, bad, monkeypatch):
    opened: list[object] = []
    monkeypatch.setattr(
        Path, "read_text", lambda self, *a, **k: opened.append(self) or ""
    )
    with pytest.raises(KeyError) as exc:
        fn(bad)
    for n in TEMPLATE_NAMES:
        assert n in str(exc.value)
    assert opened == []


def test_schema_json_parses_and_pins_schema_version():
    doc = json.loads(schema_json())
    assert doc["properties"]["schema_version"]["const"] == SCHEMA_VERSION
