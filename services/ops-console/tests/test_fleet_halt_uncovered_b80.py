"""Backlog B80: a fleet halt that NAMES its domains reports the active agents no named halt can reach.

The registry's domain filter folds ASCII case and trims spaces only. A row whose domain is a look-alike of "finance"
(stored before the registry's ASCII write rule) is in no named domain's listing, so the kill-switch never halts it, and the
completeness check, built from the same listing, used to answer all_ok: true. After every kill is sent the console now reads
the registry once more; each active row whose domain is outside the rule and that no domain report confirmed is listed by
id in ``uncovered_rows`` (never its domain text), and all_ok is false. Nothing extra is killed: the operator named the
domains; the fallback is a halt by id or a fleet halt naming no domain. A fleet halt naming no domain is unchanged: it sends
each stored domain string back exactly, so it reaches these rows."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from ops_console.api import REGISTRY_DOMAIN_RE, ServiceClient, create_app

HALT = {"operator": "CISO", "reason": "b80", "confirm": "HALT"}
LOOK = "fin" + chr(0x200B) + "ance"


class _Dead:
    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, *a, **k):
        raise ConnectionError("down")


def _console(rows, full_listing_status=200, full_listing=None):
    """rows: the registry. GET /agents?domain=d answers the rows whose domain matches d the registry's way (ASCII case,
    trimmed spaces); GET /agents with no filter answers every row (or ``full_listing_status``)."""
    seen = {"reads": [], "domains": [], "agents": []}

    def registry(request: httpx.Request) -> httpx.Response:
        wanted = request.url.params.get("domain")
        seen["reads"].append(str(wanted))
        if wanted is None:
            if full_listing is not None:
                return full_listing()
            if full_listing_status != 200:
                return httpx.Response(full_listing_status, json={"detail": "down"})
            return httpx.Response(200, json=rows)
        key = wanted.strip(" ").lower()
        return httpx.Response(200, json=[r for r in rows if isinstance(r.get("domain"), str)
                                         and r["domain"].strip(" ").lower() == key])

    def killswitch(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/kill/domain/"):
            from urllib.parse import unquote
            domain = unquote(path.rsplit("/", 1)[-1])
            seen["domains"].append(domain)
            key = domain.strip(" ").lower()
            ids = [r["agent_id"] for r in rows if isinstance(r.get("domain"), str)
                   and r["domain"].strip(" ").lower() == key and r.get("status") != "retired"]
            return httpx.Response(200, json={"domain": domain, "killed": ids,
                                             "results": [{"agent_id": i, "outcome": "killed"} for i in ids]})
        seen["agents"].append(path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"agent_id": path.rsplit("/", 1)[-1], "previous_status": "active"})

    wrap = lambda t: ServiceClient(client=httpx.Client(transport=httpx.MockTransport(t), base_url="http://t"),  # noqa: E731
                                   base_url="http://t")
    dead = ServiceClient(client=_Dead(), base_url="http://dead")
    ledger = wrap(lambda request: httpx.Response(201, json={"ok": True}))
    app = create_app(registry=wrap(registry), ledger=ledger, killswitch=wrap(killswitch), delegation=dead,
                     governor=dead, sentinel=dead, lifecycle=dead, attest=dead, crosswalk=dead, federation=dead,
                     replay=dead, gateway=dead)
    return TestClient(app), seen


def _row(aid, domain, status="active"):
    return {"agent_id": aid, "name": aid, "owner": "O", "domain": domain, "status": status}


def test_a_named_halt_that_misses_a_stored_lookalike_is_not_all_ok_and_names_it_by_id_only():
    c, seen = _console([_row("plain", "finance"), _row("legacy", LOOK)])
    r = c.post("/api/fleet/halt", json={**HALT, "domains": ["finance"]})
    out = r.json()
    assert r.status_code == 200 and seen["domains"] == ["finance"]
    assert out["results"][0]["ok"] is True              # the named domain itself was halted completely
    assert seen["agents"] == []                         # nothing the operator did not name is killed
    assert out["coverage_checked"] is True and out["uncovered_count"] == 1
    assert [u["agent_id"] for u in out["uncovered_rows"]] == ["legacy"]
    assert out["all_ok"] is False                       # before B80 this was True: the halt reported success
    assert LOOK not in r.text and "fin" + chr(0x200B) not in r.text


def test_a_named_halt_with_only_conforming_rows_is_all_ok_and_reads_the_registry_once_more_after_the_kills():
    c, seen = _console([_row("plain", "finance"), _row("p2", "Finance "), _row("other", "hr")])
    out = c.post("/api/fleet/halt", json={**HALT, "domains": ["finance"]}).json()
    assert out["all_ok"] is True and out["uncovered_count"] == 0 and out["uncovered_rows"] == []
    assert seen["reads"] == ["finance", "None"]


@pytest.mark.parametrize("status", ["retired", "killed"])
def test_a_lookalike_that_is_already_stopped_is_not_uncovered(status):
    c, _ = _console([_row("plain", "finance"), _row("legacy", LOOK, status=status)])
    out = c.post("/api/fleet/halt", json={**HALT, "domains": ["finance"]}).json()
    assert out["uncovered_count"] == 0 and out["all_ok"] is True


def test_a_lookalike_the_operator_named_literally_is_reached_and_not_uncovered():
    c, seen = _console([_row("plain", "finance"), _row("legacy", LOOK)])
    out = c.post("/api/fleet/halt", json={**HALT, "domains": ["finance", LOOK]}).json()
    assert out["uncovered_count"] == 0 and out["all_ok"] is True


def test_a_failed_full_listing_cannot_show_the_named_halt_complete_but_the_halt_is_still_sent():
    c, seen = _console([_row("plain", "finance")], full_listing_status=503)
    out = c.post("/api/fleet/halt", json={**HALT, "domains": ["finance"]}).json()
    assert seen["domains"] == ["finance"] and out["results"][0]["ok"] is True
    assert out["coverage_checked"] is False and out["all_ok"] is False


def test_a_fleet_halt_naming_no_domain_reaches_the_lookalike_and_is_unchanged():
    c, seen = _console([_row("plain", "finance"), _row("legacy", LOOK)])
    out = c.post("/api/fleet/halt", json=HALT).json()
    assert sorted(seen["domains"]) == sorted(["finance", LOOK])     # each stored domain string, sent back exactly
    assert out["all_ok"] is True and out["uncovered_count"] == 0 and out["coverage_checked"] is True
    assert seen["reads"] == ["None"]                                # one listing, no extra read


def test_the_console_copy_of_the_rule_is_the_registry_rule():
    from agent_registry.models import _NEW_DOMAIN
    assert REGISTRY_DOMAIN_RE.pattern == _NEW_DOMAIN.pattern


# --- PR 1391 round 1 (blind reviewer FIX): the console must judge a row the registry filter's way -------------------


@pytest.mark.parametrize("domain", ["finance" + chr(0x00A0), chr(9) + "finance", "finance" + chr(10)],
                         ids=["nbsp-end", "tab-start", "lf-end"])
def test_a_stored_domain_with_a_non_space_whitespace_end_makes_a_named_halt_not_green(domain):
    """SQLite trim() removes U+0020 only, so the registry listing for "finance" leaves this row out; str.strip() would have
    judged it conforming and answered all_ok true while the agent stayed active."""
    c, seen = _console([_row("plain", "finance"), _row("legacy", domain)])
    out = c.post("/api/fleet/halt", json={**HALT, "domains": ["finance"]}).json()
    assert seen["agents"] == [] and [u["agent_id"] for u in out["uncovered_rows"]] == ["legacy"]
    assert out["all_ok"] is False


def test_the_registry_filter_really_leaves_those_rows_out(tmp_path):
    """The premise, measured on the real store: SQLite trim() keeps the NBSP, TAB and LF; it drops plain spaces."""
    from agent_registry.models import AgentCreate
    from agent_registry.store import RegistryStore
    s = RegistryStore(tmp_path / "a.sqlite3")
    s.add(AgentCreate(agent_id="plain", name="P", owner="O", domain="finance"))
    for i, d in enumerate(["finance" + chr(0x00A0), chr(9) + "finance", "finance" + chr(10), " finance "]):
        s.add(AgentCreate.model_construct(agent_id=f"l{i}", name="L", owner="O", domain=d, manifest_ref=None))
    assert [r.agent_id for r in s.list(domain="finance")] == ["l3", "plain"]
    s.close()


def test_an_extra_read_that_raises_cannot_show_the_named_halt_complete():
    def boom():
        raise httpx.ConnectError("down")
    c, seen = _console([_row("plain", "finance")], full_listing=boom)
    out = c.post("/api/fleet/halt", json={**HALT, "domains": ["finance"]}).json()
    assert seen["domains"] == ["finance"] and out["coverage_checked"] is False and out["all_ok"] is False


def test_an_extra_read_answering_an_object_not_a_list_cannot_show_the_named_halt_complete():
    c, _ = _console([_row("plain", "finance")], full_listing=lambda: httpx.Response(200, json={"agents": []}))
    out = c.post("/api/fleet/halt", json={**HALT, "domains": ["finance"]}).json()
    assert out["coverage_checked"] is False and out["all_ok"] is False
