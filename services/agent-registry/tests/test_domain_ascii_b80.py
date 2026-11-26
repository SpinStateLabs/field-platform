"""Backlog B80 (Don, 2026-11-23: "Yes, ASCII only"): a NEW domain is ASCII letters and digits separated by single spaces,
'.', '_' or '-'. The registry's domain filter folds ASCII case and trims spaces only, so before this rule a look-alike
domain ("fin" + zero-width space + "ance", a Cyrillic letter, a doubled space) was accepted on write and silently missed
by a domain halt naming "finance". Pinned here: all ten look-alikes are a 422 on POST, PATCH and the CLI, the message is
fixed and never quotes the value, ordinary names still work, the existing strip-then-check order is kept, and a row
written BEFORE the rule (bypassing the model) still reads back and is still missed by the filter: the residual is real,
counted by deploy precondition P21 and reported by the ops console's named fleet halt."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.api import create_app
from agent_registry.models import DOMAIN_RULE, MAX_DOMAIN, AgentCreate, AgentUpdate
from agent_registry.store import RegistryStore

#: The ten look-alikes of "finance" measured in the B80 proposal: each was accepted on write and missed by the filter.
#: Built with chr() so this file stays plain ASCII.
LOOKALIKES = {
    "zero-width space": "fin" + chr(0x200B) + "ance",
    "zero-width non-joiner": "fin" + chr(0x200C) + "ance",
    "soft hyphen": "fin" + chr(0x00AD) + "ance",
    "word joiner": "fin" + chr(0x2060) + "ance",
    "fullwidth letter": chr(0xFF46) + "inance",
    "no-break space": "finance" + chr(0x00A0) + "x",
    "combining mark": "fina" + chr(0x0301) + "nce",
    "cyrillic a": "fin" + chr(0x0430) + "nce",
    "turkish dotted I": "F" + chr(0x0130) + "NANCE",
    "double space": "fin  ance",
}
IDS = list(LOOKALIKES)
VALUES = list(LOOKALIKES.values())

AGENT = {"agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot", "owner": "Controller", "domain": "finance"}


@pytest.fixture()
def store(tmp_path):
    s = RegistryStore(tmp_path / "agents.sqlite3")
    yield s
    s.close()


@pytest.fixture()
def client(store, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    assert c.post("/agents", json=AGENT).status_code == 201
    return c


def _refusal_is_fixed(r, value):
    assert r.status_code == 422, r.text
    assert value not in r.text and value.encode("unicode_escape").decode() not in r.text
    detail = r.json()["detail"]                       # the shared handler keeps type, loc and a fixed msg only
    assert [e["loc"][-1] for e in detail] == ["domain"], detail
    assert all(set(e) <= {"type", "loc", "msg"} for e in detail), detail


@pytest.mark.parametrize("value", VALUES, ids=IDS)
def test_a_lookalike_domain_is_refused_on_post(client, value):
    r = client.post("/agents", json={**AGENT, "agent_id": "lookalike", "domain": value})
    _refusal_is_fixed(r, value)
    assert client.get("/agents/lookalike").status_code == 404


@pytest.mark.parametrize("value", VALUES, ids=IDS)
def test_a_lookalike_domain_is_refused_on_patch_and_changes_nothing(client, value):
    before = client.get("/agents/invoicing-agent").json()
    r = client.patch("/agents/invoicing-agent", json={"domain": value})
    _refusal_is_fixed(r, value)
    assert client.get("/agents/invoicing-agent").json() == before


@pytest.mark.parametrize("value", VALUES, ids=IDS)
def test_a_lookalike_domain_is_refused_by_both_request_models(value):
    with pytest.raises(ValidationError) as create:
        AgentCreate(agent_id="a", name="n", owner="o", domain=value)
    with pytest.raises(ValidationError) as update:
        AgentUpdate(domain=value)
    for exc in (create, update):
        assert DOMAIN_RULE in str(exc.value)


@pytest.mark.parametrize("value", VALUES, ids=IDS)
def test_a_lookalike_domain_is_refused_by_the_cli_without_echo(tmp_path, monkeypatch, value):
    monkeypatch.delenv("FIELD_LEDGER_URL", raising=False)
    monkeypatch.delenv("FIELD_MANIFEST_DIR", raising=False)
    db = tmp_path / "a.sqlite3"
    r = CliRunner().invoke(cli.app, ["add", "cli-agent", "--name", "N", "--owner", "O", "--domain", value, "--path", str(db)])
    assert r.exit_code == 2, r.output
    assert "error: invalid domain" in r.output and value not in r.output
    s = RegistryStore(db)
    try:
        assert s.list() == []
    finally:
        s.close()


@pytest.mark.parametrize("value", ["finance", "FINANCE", "hr", "ops-eu", "sales.emea", "growth_2", "Customer Support",
                                   "a1", "x" * MAX_DOMAIN])
def test_ordinary_domains_are_accepted_unchanged(client, value):
    r = client.post("/agents", json={**AGENT, "agent_id": "ok", "domain": value})
    assert r.status_code == 201, r.text
    assert client.get("/agents/ok").json()["domain"] == value
    assert client.patch("/agents/ok", json={"domain": value}).status_code == 200


@pytest.mark.parametrize("value", ["-finance", "finance-", "fin..ance", "fin._ance", ".", "fin/ance", "fin" + chr(9) + "ance",
                                   "fin" + chr(10) + "ance", "x" * (MAX_DOMAIN + 1)])
def test_separator_and_length_edges_are_refused(value):
    with pytest.raises(ValidationError):
        AgentCreate(agent_id="a", name="n", owner="o", domain=value)
    with pytest.raises(ValidationError):
        AgentUpdate(domain=value)


ZWSP, NBSP, BOM = chr(0x200B), chr(0x00A0), chr(0xFEFF)


@pytest.mark.parametrize("value,stored", [(" finance ", "finance"), (ZWSP + "finance" + ZWSP, "finance"),
                                          (NBSP + "hr" + NBSP, "hr"), (BOM + "ops-eu", "ops-eu")])
def test_the_strip_then_check_order_is_kept(value, stored):
    """The blank rule trims ignorable ENDS first; the ASCII rule then checks what is left (so padding is not a 422)."""
    assert AgentCreate(agent_id="a", name="n", owner="o", domain=value).domain == stored
    assert AgentUpdate(domain=value).domain == stored


def test_the_default_domain_and_an_omitted_patch_domain_still_pass():
    assert AgentCreate(agent_id="a", name="n", owner="o").domain == "general"
    assert AgentUpdate(name="x").domain is None


def test_the_domain_rule_is_a_method_of_both_request_models():
    import ast
    import inspect

    from agent_registry import models
    tree = ast.parse(inspect.getsource(models))
    methods = {n.name: {f.name for f in n.body if isinstance(f, ast.FunctionDef)} for n in tree.body if isinstance(n, ast.ClassDef)}
    assert "_domain_shape" in methods["AgentCreate"] and "_domain_shape" in methods["AgentUpdate"]


# ---- the residual: a row stored BEFORE the rule is not re-checked, and the domain filter still misses it ---------------


@pytest.mark.parametrize("value", VALUES, ids=IDS)
def test_a_legacy_lookalike_row_still_reads_back_and_is_still_missed_by_the_domain_filter(store, value):
    store.add(AgentCreate(**{**AGENT, "agent_id": "plain"}))
    store.add(AgentCreate.model_construct(agent_id="legacy", name="L", owner="O", domain=value, manifest_ref=None))
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    assert c.get("/agents/legacy").json()["domain"] == value               # readable: AgentRecord stays lenient
    assert {a["agent_id"] for a in c.get("/agents").json()} == {"plain", "legacy"}
    assert [a["agent_id"] for a in c.get("/agents", params={"domain": "finance"}).json()] == ["plain"]
    assert [r.agent_id for r in store.list(domain="finance")] == ["plain"]


def test_a_legacy_lookalike_row_can_be_corrected_by_patch_and_is_then_found(store):
    store.add(AgentCreate.model_construct(agent_id="legacy", name="L", owner="O", domain=VALUES[0], manifest_ref=None))
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    assert c.patch("/agents/legacy", json={"domain": "finance"}).status_code == 200
    assert [a["agent_id"] for a in c.get("/agents", params={"domain": "finance"}).json()] == ["legacy"]
