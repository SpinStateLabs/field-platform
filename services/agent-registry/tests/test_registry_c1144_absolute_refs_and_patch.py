"""C-1144 (Don's ruling on PR 371, option b; Q-59 F-Q59-2 and F-Q59-3).

* An ABSOLUTE manifest_ref that fails to resolve, for any reason, is answered with the same status and the same
  reason: an existing non-manifest file, a directory and a path that does not exist cannot be told apart, so the
  registry is no existence oracle for absolute paths (the answer is the one a relative ref outside the directory
  already gets: 422, reason "missing").
* A PATCH of manifest_ref runs the containment in every operator mode, the operator layer OFF included.

Every id, key and path here is made up."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore

FIXTURE_MANIFEST = Path(__file__).parent / "fixtures" / "manifests" / "invoicing-agent.yaml"
BODY = {"name": "Probe Agent", "owner": "Controller, Spin State Labs", "domain": "finance"}


class _Ledger:
    def append(self, event_type, payload=None, agent_id=None):
        return None


@pytest.fixture()
def env(tmp_path, monkeypatch):
    d = tmp_path / "manifests"
    d.mkdir()
    (d / "good.yaml").write_bytes(FIXTURE_MANIFEST.read_bytes())
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "elsewhere.yaml").write_bytes(FIXTURE_MANIFEST.read_bytes())
    (outside / "not-a-manifest.txt").write_text("this is not a manifest\n", encoding="utf-8")
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(d))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    client = TestClient(create_app(store=RegistryStore(tmp_path / "agents.sqlite3"), ledger=_Ledger()))
    return client, d, outside


def _post(client, agent_id, **over):
    return client.post("/agents", json={"agent_id": agent_id, **BODY, **over})


def _absolute_failures(d: Path, outside: Path) -> list[str]:
    return [
        str(outside / "not-a-manifest.txt"),        # exists, not a manifest
        str(outside),                               # exists, a directory
        str(outside / "no-such-file.yaml"),         # does not exist
        str(d.parent / "no-such-dir" / "x.yaml"),   # its directory does not exist either
    ]


def test_every_failing_absolute_ref_is_answered_alike_on_post(env):
    client, d, outside = env
    answers = []
    for i, ref in enumerate(_absolute_failures(d, outside)):
        r = _post(client, f"abs-{i}", manifest_ref=ref)
        answers.append((r.status_code, r.json()["detail"]["reason"]))
        assert client.get(f"/agents/abs-{i}").status_code == 404          # nothing was written
    assert len(set(answers)) == 1, answers
    assert answers[0] == (422, "missing")


def test_an_existing_non_manifest_file_and_a_missing_one_are_not_told_apart_by_the_422_body(env):
    client, d, outside = env
    exists = _post(client, "twin-1", manifest_ref=str(outside / "not-a-manifest.txt"))
    nothing = _post(client, "twin-2", manifest_ref=str(outside / "no-such-file.yaml"))
    for r in (exists, nothing):
        assert r.status_code == 422
        body = dict(r.json()["detail"])
        body.pop("manifest_ref")                 # the body echoes the caller's own ref, which differs by design
        assert body == {"error": "manifest_ref does not resolve", "reason": "missing", "hint": body["hint"]}
    assert exists.json()["detail"]["hint"] == nothing.json()["detail"]["hint"]


def test_a_relative_ref_inside_the_directory_still_tells_missing_from_invalid(env):
    """The ruling covers absolute refs only: inside FIELD_MANIFEST_DIR the split is harmless and stays."""
    client, d, _ = env
    (d / "broken.yaml").write_text("not: [valid", encoding="utf-8")
    assert _post(client, "rel-1", manifest_ref="nope.yaml").json()["detail"]["reason"] == "missing"
    assert _post(client, "rel-2", manifest_ref="broken.yaml").json()["detail"]["reason"] == "invalid"


def test_a_good_absolute_ref_outside_is_still_accepted(env):
    client, d, outside = env
    assert _post(client, "abs-ok", manifest_ref=str(outside / "elsewhere.yaml")).status_code == 201


def test_with_the_operator_layer_off_a_patch_to_a_relative_ref_outside_is_refused_as_missing(env):
    """F-Q59-3 as ruled: containment runs on EVERY PATCH of a manifest_ref. Before C-1144 this answered 200 and the
    ref was stored, so register-then-PATCH bypassed the containment."""
    client, d, outside = env
    assert _post(client, "off-1", manifest_ref="good.yaml").status_code == 201
    for ref in ("../outside/elsewhere.yaml", "sub/../../outside/elsewhere.yaml"):
        r = client.patch("/agents/off-1", json={"manifest_ref": ref})
        assert r.status_code == 422, (ref, r.text)
        assert r.json()["detail"]["reason"] == "missing"
    assert client.get("/agents/off-1").json()["manifest_ref"] == "good.yaml"


def test_with_the_operator_layer_off_a_patch_inside_the_directory_still_works(env):
    """The containment is the only check added outside ENFORCE: an unresolvable relative ref inside is still
    accepted (the declared limit pinned in test_registry_reaudit_c635.py)."""
    client, d, _ = env
    assert _post(client, "off-2", manifest_ref="good.yaml").status_code == 201
    r = client.patch("/agents/off-2", json={"manifest_ref": "nope.yaml"})
    assert r.status_code == 200 and r.json()["manifest_ref"] == "nope.yaml"
    assert client.patch("/agents/off-2", json={"manifest_ref": "good.yaml"}).status_code == 200


def test_under_enforce_every_failing_absolute_ref_is_answered_alike_on_patch(env, monkeypatch, tmp_path):
    from field_core import operator_auth as oa
    client, d, outside = env
    assert _post(client, "enf-1", manifest_ref="good.yaml").status_code == 201
    key = "tkv-c1144-key-0123456789abcdefghij"      # made up, this test only
    rows = [{"operator_id": "svc-registry-edit", "key_sha256": oa.key_sha256(key), "status": "active",
             "scopes": ["registry_edit", "bypass_operator_list"]}]
    (tmp_path / "operators.json").write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(tmp_path / "operators.json"))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    headers = {oa.HEADER_OPERATOR: "svc-registry-edit", oa.HEADER_KEY: key}
    answers = []
    for ref in _absolute_failures(d, outside):
        r = client.patch("/agents/enf-1", json={"manifest_ref": ref}, headers=headers)
        answers.append((r.status_code, r.json()["detail"]["reason"]))
    assert len(set(answers)) == 1 and answers[0] == (422, "missing"), answers
    ok = client.patch("/agents/enf-1", json={"manifest_ref": str(outside / "elsewhere.yaml")}, headers=headers)
    assert ok.status_code == 200, ok.text


def test_a_sibling_directory_sharing_the_manifest_dir_name_prefix_is_outside(env, tmp_path):
    """Reviewer F3 (M08): containment is by path relationship, not by string prefix. ``manifests_sibling`` starts with
    ``manifests`` but is not inside it; a ref into it is refused 422 "missing" on POST and on PATCH."""
    client, d, _ = env
    sibling = tmp_path / (d.name + "_sibling")
    sibling.mkdir()
    (sibling / "x.yaml").write_bytes(FIXTURE_MANIFEST.read_bytes())
    ref = "../" + sibling.name + "/x.yaml"
    r = _post(client, "sibling-probe", manifest_ref=ref)
    assert r.status_code == 422 and "missing" in r.text
    assert _post(client, "inside-probe", manifest_ref="good.yaml").status_code == 201
    r = client.patch("/agents/inside-probe", json={"manifest_ref": ref})
    assert r.status_code == 422 and "missing" in r.text
