"""S6-7: ``PATCH /agents/{id}`` resolves a ``manifest_ref`` it carries and refuses it 422 when an operator mode is ARMED
(log-only or enforce); with the operator mode OFF it does not. The README row and SPEC say so; this pins the split
side by side, and pins the docs so an edit cannot make them drift again."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa

KEY = "fok_don-key-0123456789abcdef"
HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "manifests" / "invoicing-agent.yaml"
BODY = {"agent_id": "a1", "name": "a1", "owner": "Controller", "domain": "finance"}


class Ledger:
    def append(self, *a, **k):
        pass


@pytest.fixture(autouse=True)
def mdir(tmp_path, monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)
    d = tmp_path / "mdir"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "good.yaml").write_bytes(FIXTURE.read_bytes())
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(d))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    return d


def arm(tmp_path, monkeypatch, mode):
    if mode == "off":
        return {}
    p = tmp_path / "operators.json"
    p.write_text(json.dumps([{"operator_id": "don", "key_sha256": oa.key_sha256(KEY), "status": "active",
                              "scopes": ["*"]}]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")
        return {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY}
    return {}                                   # log-only: the credential is evaluated, not required


def rig(tmp_path, monkeypatch, mode):
    headers = arm(tmp_path, monkeypatch, mode)
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"), ledger=Ledger()))
    assert c.post("/agents", json=BODY, headers=headers).status_code == 201
    return c, headers


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_armed_an_unresolvable_ref_is_refused_422_and_not_stored(tmp_path, monkeypatch, mode):
    c, h = rig(tmp_path, monkeypatch, mode)
    r = c.patch("/agents/a1", json={"manifest_ref": "sub/absent.yaml"}, headers=h)
    assert r.status_code == 422, r.text
    assert c.get("/agents/a1").json()["manifest_ref"] in (None, "")


def test_off_an_unresolvable_ref_is_not_checked(tmp_path, monkeypatch):
    c, h = rig(tmp_path, monkeypatch, "off")
    r = c.patch("/agents/a1", json={"manifest_ref": "sub/absent.yaml"}, headers=h)
    assert r.status_code == 200
    assert c.get("/agents/a1").json()["manifest_ref"] == "sub/absent.yaml"


@pytest.mark.parametrize("mode", ["off", "log-only", "enforce"])
def test_a_resolvable_ref_is_accepted_in_every_mode(tmp_path, monkeypatch, mode):
    c, h = rig(tmp_path, monkeypatch, mode)
    assert c.patch("/agents/a1", json={"manifest_ref": "sub/good.yaml"}, headers=h).status_code == 200
    assert c.get("/agents/a1").json()["manifest_ref"] == "sub/good.yaml"


# ---- the text says what the code does ----------------------------------------------------------------------------------

def _row():
    text = (HERE.parent / "README.md").read_text(encoding="utf-8")
    return next(ln for ln in text.splitlines() if ln.startswith("| `manifest_ref` keeps pointing"))


def test_the_readme_row_names_the_armed_check_and_the_off_gap():
    row = _row()
    assert "operator mode is armed" in row and "422" in row
    assert "FIELD_OPERATOR_REGISTRY" in row and "FIELD_OPERATOR_REQUIRE" in row
    assert "OFF" in row and "does NOT check it" in row
    assert "does not re-check it" not in row                  # the old unconditional claim
    assert "FIELD_OPERATOR_MODE" not in row                    # there is no such variable


def test_the_spec_and_the_code_comment_no_longer_say_patch_is_never_checked():
    spec = (HERE.parent / "SPEC.md").read_text(encoding="utf-8")
    assert "PATCH is\n  not checked (README LIMITS)" not in spec
    assert "operator mode" in spec.split("registry add` exits 2 on the same rule.")[1][:200]
    api = (HERE.parent / "src" / "agent_registry" / "api.py").read_text(encoding="utf-8")
    assert "PATCH itself is not checked" not in api
