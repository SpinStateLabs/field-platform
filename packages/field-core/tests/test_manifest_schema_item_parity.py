"""S8-2: the manifest models enforce what the vendored JSON Schema says, per item and per type.

`field validate` runs only the pydantic models (field-core has no jsonschema dependency), and the models accepted what the
schema rejects: an empty string in deny_patterns, session_written_exec_allow or protected_paths (an empty regex matches every
command or path, so `deny_patterns: ['']` validated clean), and string-typed integers and booleans (`retention_days: '30'`,
`isolated: 'no'`) through pydantic's lax coercion. Strictness is applied to the schema's integer and boolean fields only
(a float limit such as `500` or `1.5` is unaffected). The array test is driven by the schema itself, so a new minLength bound
that the models miss is caught here."""

import copy
import json

import pytest
from pydantic import ValidationError

from field_core.manifest import FieldManifest
from field_core.templates_api import schema_json, template_data


def _array_paths_with_item_min_length(node, path=()):
    found = []
    if isinstance(node, dict):
        items = node.get("items")
        if node.get("type") == "array" and isinstance(items, dict) and "minLength" in items:
            found.append(path)
        for key, value in node.items():
            if key in ("properties",):
                for name, sub in value.items():
                    found += _array_paths_with_item_min_length(sub, path + (name,))
            elif key == "items":
                found += _array_paths_with_item_min_length(value, path + ("[]",))
    return found


SCHEMA = json.loads(schema_json())
PATHS = [p for p in _array_paths_with_item_min_length(SCHEMA) if "[]" not in p]


def base():
    data = copy.deepcopy(template_data("default"))
    data["enforcement"]["irreversible_actions"] = {"deny_patterns": ["rm -rf"], "session_written_exec_allow": ["ok.sh"]}
    data["enforcement"]["protected_paths"] = [".env"]
    return data


def put(data, path, value):
    node = data
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def test_the_schema_has_the_three_known_item_bounds():
    assert set(PATHS) >= {
        ("enforcement", "irreversible_actions", "deny_patterns"),
        ("enforcement", "irreversible_actions", "session_written_exec_allow"),
        ("enforcement", "protected_paths"),
    }


def test_the_base_manifest_validates():
    FieldManifest.model_validate(base())


@pytest.mark.parametrize("path", PATHS, ids=["/".join(p) for p in PATHS])
def test_every_schema_array_with_a_minimum_item_length_rejects_an_empty_item(path):
    data = base()
    put(data, path, ["fine", ""])
    with pytest.raises(ValidationError):
        FieldManifest.model_validate(data)
    put(data, path, [""])
    with pytest.raises(ValidationError):
        FieldManifest.model_validate(data)
    put(data, path, ["x"])
    FieldManifest.model_validate(data)               # a one-character item is allowed


@pytest.mark.parametrize("path, value", [
    (("ledger", "retention_days"), "30"),
    (("ledger", "retention_days"), 30.0),
    (("ledger", "retention_days"), True),
    (("federated", "isolated"), "no"),
    (("federated", "isolated"), 0),
    (("enforcement", "rate_limits"), [{"action": "a", "max": "5", "period": "hour"}]),
    (("enforcement", "kill_switch", "sentinel_max_age_s"), "60"),
], ids=["retention-str", "retention-float", "retention-bool", "isolated-str", "isolated-int", "rate-max-str",
        "sentinel-age-str"])
def test_a_string_or_wrong_typed_integer_or_boolean_is_refused(path, value):
    data = base()
    put(data, ("federated", "allowed_peers"), [{"agent_id": "p", "trust_basis": "contract"}])   # so isolated is judged on its type
    put(data, path, value)
    with pytest.raises(ValidationError):
        FieldManifest.model_validate(data)


def test_real_integers_and_booleans_and_a_float_limit_still_validate():
    data = base()
    put(data, ("ledger", "retention_days"), 365)
    put(data, ("federated", "isolated"), True)
    put(data, ("federated", "allowed_peers"), [{"agent_id": "p", "trust_basis": "contract"}])
    put(data, ("enforcement", "rate_limits"), [{"action": "a", "max": 5, "period": "hour"}])
    for limit in (500, 500.5, 0.5):
        put(data, ("enforcement", "spend_cap"), {"currency": "USD", "limit": limit, "period": "daily"})
        FieldManifest.model_validate(data)


def test_every_shipped_template_still_validates():
    from field_core.templates_api import TEMPLATE_NAMES
    for name in TEMPLATE_NAMES:
        FieldManifest.model_validate(template_data(name))
