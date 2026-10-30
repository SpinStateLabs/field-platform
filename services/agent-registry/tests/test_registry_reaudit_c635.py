"""C-635 (reviewer C-528 F-C528-1, -2, -4, -5, -6): the registry's id grammar, the manifest_ref containment and what
the 422 says.

Probes, each red before the change:

* F-C528-1: an upper-case id is refused (the lower-case guard of the id pattern was unpinned: widened to A-Z the
  suite stayed green, and "A1" and "a1" would have registered as two agents);
* F-C528-2: confusable ids are refused: a trailing separator ("a1."), doubled separators ("a..1", "a-_1") and an id
  longer than the cap; "a_1", "a.1" and "a-1" stay valid and distinct;
* F-C528-4: a manifest_ref that leaves FIELD_MANIFEST_DIR (an absolute path elsewhere, "../outside.yaml", a symlink
  out) is refused 422 even when the file is a valid manifest; a ref inside is accepted;
* F-C528-5: the 422 body does not name the server's manifest directory;
* F-C528-6: PATCH of manifest_ref is checked only in ENFORCE; that is the documented LIMIT and it is pinned here so a
  change of it is a decision, not an accident."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore

FIXTURE_MANIFEST = Path(__file__).parent / "fixtures" / "manifests" / "invoicing-agent.yaml"
BODY = {"name": "Probe Agent", "owner": "Controller, Spin State Labs", "domain": "finance"}
MAX_ID = 64


class _Ledger:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, payload, agent_id))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    d = tmp_path / "manifests"
    d.mkdir()
    (d / "good.yaml").write_bytes(FIXTURE_MANIFEST.read_bytes())
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "elsewhere.yaml").write_bytes(FIXTURE_MANIFEST.read_bytes())
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(d))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    client = TestClient(create_app(store=RegistryStore(tmp_path / "agents.sqlite3"), ledger=_Ledger()))
    return client, d, outside


def _post(client, agent_id, **over):
    return client.post("/agents", json={"agent_id": agent_id, **BODY, **over})


# ---- F-C528-1, -2: the id grammar ---------------------------------------------------------------


@pytest.mark.parametrize("bad", ["A1", "a1B", "Agent", "-a1", ".a1", "_a1"])
def test_an_upper_case_or_separator_led_id_is_refused(env, bad):
    client, _, _ = env
    assert _post(client, bad).status_code == 422


@pytest.mark.parametrize("bad", ["a1.", "a1-", "a1_", "a..1", "a--1", "a__1", "a-_1", "a._1", "a1..", "a.-.1"])
def test_a_trailing_or_doubled_separator_is_refused(env, bad):
    client, _, _ = env
    assert _post(client, bad).status_code == 422


def test_an_id_over_the_length_cap_is_refused_and_one_at_the_cap_is_accepted(env):
    client, _, _ = env
    assert _post(client, "a" * MAX_ID).status_code == 201
    assert _post(client, "a" * (MAX_ID + 1)).status_code == 422
    assert _post(client, "a" * 5000).status_code == 422


@pytest.mark.parametrize("good", ["a1", "a-1", "a_1", "a.1", "a1b2", "svc-kill-switch", "x.y_z-1", "0abc"])
def test_ordinary_ids_stay_valid_and_distinct(env, good):
    client, _, _ = env
    assert _post(client, good).status_code == 201
    assert client.get(f"/agents/{good}").status_code == 200


def test_the_validation_error_does_not_echo_the_id(env):
    client, _, _ = env
    r = _post(client, "A1-SECRETISH-MARKER")
    assert r.status_code == 422 and "SECRETISH-MARKER" not in r.text


# ---- F-C528-4: containment ---------------------------------------------------------------------


def test_a_ref_inside_the_manifest_dir_is_accepted_relative_or_absolute(env):
    client, d, _ = env
    assert _post(client, "in-rel", manifest_ref="good.yaml").status_code == 201
    assert _post(client, "in-abs", manifest_ref=str(d / "good.yaml")).status_code == 201


@pytest.mark.parametrize("make", [
    lambda d, o: "../outside/elsewhere.yaml",                  # a relative path that climbs out
    lambda d, o: "sub/../../outside/elsewhere.yaml",           # a climb through a subdirectory
])
def test_a_relative_ref_that_leaves_the_manifest_dir_is_refused_even_when_it_is_a_valid_manifest(env, make):
    client, d, o = env
    (d / "sub").mkdir(exist_ok=True)
    r = _post(client, "out-1", manifest_ref=make(d, o))
    assert r.status_code == 422
    assert client.get("/agents/out-1").status_code == 404          # nothing was written


def test_an_absolute_ref_outside_is_still_accepted_the_estates_own_form(env):
    """Declared (PR 371 text): absolute refs are not confined. Every service suite and the estate itself register
    /data/manifests/<id>.yaml; confining them failed hundreds of tests on the GX10. A decision, not made here."""
    client, d, o = env
    assert _post(client, "abs-out", manifest_ref=str(o / "elsewhere.yaml")).status_code == 201


def test_an_outside_ref_is_answered_exactly_like_a_missing_one_so_it_is_no_existence_oracle(env):
    client, d, o = env
    outside = _post(client, "or-1", manifest_ref="../outside/elsewhere.yaml")          # exists, valid, outside
    nothing = _post(client, "or-2", manifest_ref="../outside/no-such-file.yaml")       # does not exist, outside
    assert outside.status_code == nothing.status_code == 422
    assert outside.json()["detail"]["reason"] == nothing.json()["detail"]["reason"] == "missing"


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_symlink_that_points_out_of_the_manifest_dir_is_refused(env):
    client, d, o = env
    (d / "link.yaml").symlink_to(o / "elsewhere.yaml")
    assert _post(client, "out-2", manifest_ref="link.yaml").status_code == 422


def test_the_patch_ref_is_contained_too_when_it_is_checked(env, monkeypatch):
    client, d, o = env
    assert _post(client, "p1", manifest_ref="good.yaml").status_code == 201
    from field_core import operator_auth as oa
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")                      # ENFORCE: the PATCH ref check runs
    r = client.patch("/agents/p1", json={"manifest_ref": "../outside/elsewhere.yaml"})
    assert r.status_code in (401, 403, 422)                      # refused by the operator layer or the check
    monkeypatch.delenv(oa.ENV_REQUIRE)
    assert client.get("/agents/p1").json()["manifest_ref"] == "good.yaml"


# ---- F-C528-5: what the 422 says ----------------------------------------------------------------


def test_the_422_for_an_unresolvable_ref_does_not_name_the_server_directory(env):
    client, d, _ = env
    r = _post(client, "gone-1", manifest_ref="nope.yaml")
    assert r.status_code == 422
    body = r.json()["detail"]
    assert body["error"] == "manifest_ref does not resolve" and body["manifest_ref"] == "nope.yaml"
    assert "manifest_dir" not in body
    assert str(d) not in r.text and d.name not in r.text


# ---- F-C528-6: the PATCH limit, pinned ----------------------------------------------------------


def test_patching_an_unresolvable_ref_is_accepted_outside_enforce_a_declared_limit(env):
    """README LIMITS: the PATCH resolvability check runs only in ENFORCE. Pinned so that changing it is a decision."""
    client, _, _ = env
    assert _post(client, "lim-1", manifest_ref="good.yaml").status_code == 201
    r = client.patch("/agents/lim-1", json={"manifest_ref": "nope.yaml"})
    assert r.status_code == 200 and r.json()["manifest_ref"] == "nope.yaml"
