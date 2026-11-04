"""S5-8: name, owner, domain and attested_by are stripped, non-blank and bounded, and manifest_ref is bounded (not stripped: a
whitespace ref is SET and the resolver refuses it), at the request boundary (POST, PATCH, attest). A 422 never echoes the input. AgentRecord stays lenient, so a legacy row (a
5000-character name, a whitespace owner) still reads and never makes a GET 500."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.models import AgentCreate
from agent_registry.store import RegistryStore

MARK = "SECRET-INPUT-MARKER-0f3a"
LIMITS = {"name": 200, "owner": 200, "domain": 64, "manifest_ref": 512}
BASE = {"agent_id": "a1", "name": "Invoicing", "owner": "AP Team Lead", "domain": "finance"}


@pytest.fixture()
def reg(tmp_path):
    path = tmp_path / "agents.sqlite3"
    store = RegistryStore(path)
    with TestClient(create_app(store=store)) as c:
        c.post("/agents", json=BASE)
        yield c, path
    store.close()


def post(c, **over):
    body = {**BASE, "agent_id": "a2", **over}
    return c.post("/agents", json=body)


# ---- POST -----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["name", "owner", "domain"])
@pytest.mark.parametrize("blank", ["", " ", "   ", "\t\n ", " "])
def test_a_blank_required_text_is_422(reg, field, blank):
    c, _ = reg
    assert post(c, **{field: blank}).status_code == 422


@pytest.mark.parametrize("field,limit", sorted(LIMITS.items()))
def test_the_limit_is_accepted_and_one_over_is_422_without_echo(reg, field, limit):
    c, _ = reg
    if field == "manifest_ref":
        # a SET ref must also resolve (D3b), so the at-limit case is asserted on the request model
        assert AgentCreate(**{**BASE, "manifest_ref": "m" * limit}).manifest_ref == "m" * limit
    else:
        ok = post(c, **{field: "x" * limit})
        assert ok.status_code == 201, ok.text
    over = post(c, **{field: MARK + "y" * limit})
    assert over.status_code == 422
    assert MARK not in over.text


def test_an_over_long_manifest_ref_is_422_by_length_not_by_resolution(reg):
    c, _ = reg
    r = post(c, manifest_ref="m" * 513)
    assert r.status_code == 422
    assert any(e["loc"][-1] == "manifest_ref" and "at most 512" in e["msg"] for e in r.json()["detail"]), r.text


def test_text_is_stored_stripped(reg):
    c, _ = reg
    r = post(c, name="  Invoicing Copilot  ", owner="\tAP Team Lead\n", domain=" finance ")
    assert r.status_code == 201, r.text
    got = c.get("/agents/a2").json()
    assert (got["name"], got["owner"], got["domain"]) == ("Invoicing Copilot", "AP Team Lead", "finance")


def test_a_value_that_is_only_long_because_of_padding_is_accepted(reg):
    c, _ = reg
    r = post(c, name=" " * 50 + "x" * 200 + " " * 50)
    assert r.status_code == 201 and len(r.json()["name"]) == 200


def test_the_default_domain_and_a_missing_manifest_ref_are_unchanged(reg):
    c, _ = reg
    r = c.post("/agents", json={"agent_id": "a3", "name": "n", "owner": "o"})
    assert r.status_code == 201 and r.json()["domain"] == "general" and r.json()["manifest_ref"] is None


# ---- PATCH ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["name", "owner", "domain"])
@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_patch_blank_is_422_and_the_row_is_unchanged(reg, field, blank):
    c, _ = reg
    before = c.get("/agents/a1").json()
    assert c.patch("/agents/a1", json={field: blank}).status_code == 422
    assert c.get("/agents/a1").json() == before


@pytest.mark.parametrize("field,limit", [("name", 200), ("owner", 200), ("domain", 64), ("manifest_ref", 512)])
def test_patch_over_long_is_422_without_echo(reg, field, limit):
    c, _ = reg
    r = c.patch("/agents/a1", json={field: MARK + "y" * limit})
    assert r.status_code == 422 and MARK not in r.text


def test_patch_stores_stripped_and_an_omitted_field_stays(reg):
    c, _ = reg
    r = c.patch("/agents/a1", json={"owner": "  New Owner  ", "domain": " ops "})
    assert r.status_code == 200
    got = c.get("/agents/a1").json()
    assert (got["owner"], got["domain"], got["name"]) == ("New Owner", "ops", "Invoicing")


def test_patch_explicit_null_is_still_allowed_where_it_was(reg):
    c, _ = reg
    assert c.patch("/agents/a1", json={"manifest_ref": None}).status_code == 200


# ---- attest ---------------------------------------------------------------------------------------------------------

def test_attested_by_limit_and_stripping(reg):
    c, _ = reg
    assert c.post("/agents/a1/attest", json={"attested_by": "x" * 201}).status_code == 422
    over = c.post("/agents/a1/attest", json={"attested_by": MARK + "y" * 200})
    assert over.status_code == 422 and MARK not in over.text
    ok = c.post("/agents/a1/attest", json={"attested_by": "  " + "x" * 200 + "  "})
    assert ok.status_code == 200 and ok.json()["attested_by"] == "x" * 200


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_attester_is_still_422(reg, blank):
    c, _ = reg
    assert c.post("/agents/a1/attest", json={"attested_by": blank}).status_code == 422


# ---- legacy rows stay readable ----------------------------------------------------------------------------------------

def test_a_legacy_row_with_a_huge_name_and_a_blank_owner_still_reads(reg):
    c, path = reg
    con = sqlite3.connect(path)
    con.execute("INSERT INTO agents (agent_id, name, owner, domain, manifest_ref, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("legacy", "n" * 5000, "   ", "", "r" * 2000, "active", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))
    con.commit()
    con.close()
    got = c.get("/agents/legacy")
    assert got.status_code == 200 and len(got.json()["name"]) == 5000
    assert c.get("/agents").status_code == 200
    assert c.get("/health").status_code == 200
