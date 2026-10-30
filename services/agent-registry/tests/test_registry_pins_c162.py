"""C-162 (reviewer C-155 F-C155-2/-3/-4): survivors pinned inside the registry's own suite.

* `on_behalf_of` (api.py): the scope check is a second line behind field-core's own
  `_acts_for_others`, so the HTTP tests cannot see it; it is pinned directly.
* `attest_agent` (api.py): the ENFORCE list check, so a narrow "attest" identity cannot
  reset the re-attestation clock of an agent whose manifest does not name it.
* `install_authn` (api.py): a request without the perimeter secret gets 401.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from agent_registry import api as registry_api
from agent_registry.api import create_app, on_behalf_of
from agent_registry.store import RegistryStore
from field_core import authn
from field_core import operator_auth as oa
from field_core.templates_api import template_data

OBO = registry_api.ON_BEHALF_HEADER
KEY_DON = "tkv-c162don-key-0123456789abcdef"
KEY_ATT = "tkv-c162att-key-0123456789abcdef"
KEY_BYP = "tkv-c162byp-key-0123456789abcdef"
ATT = {"attested_by": "Don Hagell"}


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE, authn.ENV_VAR):
        monkeypatch.delenv(n, raising=False)


def _auth(operator_id, *scopes):
    return oa.OperatorAuth(mode=oa.ENFORCE, operator_id=operator_id, scopes=tuple(scopes))


# --- F-C155-2: on_behalf_of ----------------------------------------------------------


@pytest.mark.parametrize("scopes", [("*",), ("kill", "revive"), ()])
def test_an_authenticated_identity_without_bypass_has_the_header_ignored(scopes):
    assert on_behalf_of({OBO: "don"}, _auth("killer", *scopes)) is None
    assert on_behalf_of(Headers({OBO: "don"}), _auth("killer", *scopes)) is None


def test_an_unauthenticated_caller_has_the_header_ignored_even_if_scopes_are_set():
    assert on_behalf_of({OBO: "don"}, _auth(None, "bypass_operator_list")) is None


def test_a_bypass_identity_names_the_operator_from_either_header_shape():
    bypass = _auth("svc-killswitch", "kill", "bypass_operator_list")
    assert on_behalf_of(Headers({OBO: "don"}), bypass) == "don"
    # a plain dict (no getlist): the header name matches in any case
    assert on_behalf_of({"X-Field-Operator-On-Behalf-Of": "don"}, bypass) == "don"
    assert on_behalf_of({"x-other": "don"}, bypass) is None


# --- F-C155-3: the attest ENFORCE list check -----------------------------------------


def _manifest(tmp_path, authorized):
    data = template_data("default")
    data["agent"]["name"] = "g1"
    data["enforcement"]["kill_switch"]["authorized_operators"] = authorized
    path = tmp_path / "g1.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture()
def guarded(tmp_path, monkeypatch):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
         "scopes": ["*"]},
        {"operator_id": "att", "key_sha256": oa.key_sha256(KEY_ATT), "status": "active",
         "scopes": ["attest"]},
        {"operator_id": "byp", "key_sha256": oa.key_sha256(KEY_BYP), "status": "active",
         "scopes": ["attest", "bypass_operator_list"]},
    ]
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps(rows), encoding="utf-8")
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3")))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                   "domain": "finance"}).status_code == 201
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    assert c.patch("/agents/a1", json={"manifest_ref": str(_manifest(tmp_path, ["don"]))},
                   headers=_hdr("don", KEY_DON)).status_code == 200
    return c


def _attested_at(c):
    return c.get("/agents/a1").json()["attested_at"]


def test_attest_by_an_identity_the_manifest_does_not_name_is_refused(guarded):
    c = guarded
    before = _attested_at(c)
    assert c.post("/agents/a1/attest", json=ATT, headers=_hdr("att", KEY_ATT)).status_code == 403
    assert _attested_at(c) == before


def test_attest_by_the_named_operator_or_a_bypass_identity_is_accepted(guarded):
    c = guarded
    assert c.post("/agents/a1/attest", json=ATT, headers=_hdr("don", KEY_DON)).status_code == 200
    assert c.post("/agents/a1/attest", json=ATT, headers=_hdr("byp", KEY_BYP)).status_code == 200


def test_attest_of_an_unregistered_agent_under_enforce_is_404(guarded):
    r = guarded.post("/agents/nosuch/attest", json=ATT, headers=_hdr("don", KEY_DON))
    assert r.status_code == 404


def test_the_list_check_is_enforce_only(tmp_path, monkeypatch):
    """Log-only is unchanged: an identity off the list is not refused by the list check."""
    rows = [{"operator_id": "att", "key_sha256": oa.key_sha256(KEY_ATT), "status": "active",
             "scopes": ["attest"]}]
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps(rows), encoding="utf-8")
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3")))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                   "domain": "finance",
                                   "manifest_ref": str(_manifest(tmp_path, ["don"]))}
                  ).status_code == 201
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))  # no ENV_REQUIRE: log-only
    assert c.post("/agents/a1/attest", json=ATT, headers=_hdr("att", KEY_ATT)).status_code == 200


# --- F-C155-4: the perimeter secret --------------------------------------------------


def test_a_request_without_the_perimeter_secret_gets_401(tmp_path, monkeypatch):
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3")))
    monkeypatch.setenv(authn.ENV_VAR, "tkv-c162-perimeter-secret")
    assert c.get("/agents").status_code == 401
    assert c.get("/agents", headers={authn.HEADER: "wrong"}).status_code == 401
    assert c.get("/agents", headers={authn.HEADER: "tkv-c162-perimeter-secret"}).status_code == 200
    assert c.get("/health").status_code == 200  # the one open path
