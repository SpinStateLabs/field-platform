"""v1.2 D3 — API-key inventory scan and secrets-text scan.

Every guard here has a test that fails if the guard is removed:

* the owner rule applies EVEN when a key is named after a registered agent;
* matching is case-insensitive EXACT (a substring of an owner is not the owner);
* ``last_used_by`` must be an owner, agent id or agent name;
* patterns are ordered and a span is counted once (``sk-ant-`` never also ``sk-``);
* patterns refuse to start (and, at fixed lengths, end) inside a longer token;
* every hit is redacted by the MODEL, so no serialisation path carries a raw value;
* ``DiscoverRequest`` forbids extra fields and every input is capped at 1 MiB.

Synthetic credentials are assembled at run time from split literals, so no
provider-shaped token sits contiguous in this file (GitHub push protection);
each carries ``SYNTHETIC``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.api import create_app
from agent_registry.discover import (
    REASON_LAST_USED_BY,
    REASON_OWNER,
    REASON_UNOWNED,
    scan_api_keys,
    scan_secrets_text,
)
from agent_registry.models import AgentRecord, SecretHit, ShadowCandidate
from agent_registry.redaction import KEY_PATTERNS, MAX_SCAN_BYTES
from agent_registry.store import RegistryStore

FIXTURES = Path(__file__).parent / "fixtures"
HEADER = "key_name,owner,service,created,last_used,last_used_by"

S = "SYNTHETIC"
#: One synthetic value per provider pattern, keyed by the pattern name.
SYNTHETIC = {
    "anthropic": "sk-" + "ant-api03-" + (S * 5)[:40],
    "openai-style-sk": "sk-" + "proj-" + S * 3,
    "google-api-key": "AI" + "za" + (S + "0") * 3 + S[:5],
    "huggingface": "hf" + "_" + S * 4,
    "aws-access-key-id": "AK" + "IA" + S + "0000000",
    "github-token": "gh" + "p_" + S * 4,
    "slack-token": "xo" + "xb-" + "0000-" + S,
    "stripe-secret-key": "sk" + "_live_" + S * 2,
    "google-oauth-access-token": "ya" + "29." + S * 3,
    "jwt": "ey" + "J" + S + ".ey" + "J" + S + "." + S + "sig",
}


def _agents() -> list[AgentRecord]:
    return [AgentRecord(agent_id="invoicing-agent", name="Invoice Drafting Copilot",
                        owner="Controller, Spin State Labs", domain="finance")]


def _csv(*rows: str) -> str:
    return "\n".join((HEADER, *rows)) + "\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(tmp_path / "agents.sqlite3")
    c = TestClient(create_app(store=store))
    assert c.post("/agents", json={
        "agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
        "owner": "Controller, Spin State Labs", "domain": "finance"}).status_code == 201
    yield c
    store.close()


# --- the synthetic values are what they claim to be ---------------------------

def test_every_provider_pattern_has_a_synthetic_value_and_each_is_synthetic():
    assert set(SYNTHETIC) == {p.name for p in KEY_PATTERNS}
    assert all(S in v for v in SYNTHETIC.values())


# --- scan_api_keys: the owner rules --------------------------------------------

def test_adversarial_key_named_after_a_registered_agent_is_surfaced_by_owner():
    """`invoicing-agent` is registered, but its NAME is not what owns a key:
    a key called invoicing-agent-prod owned by growth@ is a shadow credential."""
    candidates, scanned = scan_api_keys(
        _csv("invoicing-agent-prod,growth@example.test,anthropic,2026-08-01,2026-09-12,"),
        _agents())
    assert scanned == 1
    assert [c.identifier for c in candidates] == ["invoicing-agent-prod"]
    assert candidates[0].reason == REASON_OWNER
    assert candidates[0].source == "api-keys"
    assert candidates[0].evidence["owner"] == "growth@example.test"


def test_owner_match_is_not_surfaced_and_matching_is_case_insensitive():
    candidates, scanned = scan_api_keys(
        _csv('k1,"Controller, Spin State Labs",anthropic,,,',
             'k2,"  CONTROLLER, spin state labs ",anthropic,,,'),
        _agents())
    assert scanned == 2 and candidates == []


def test_a_substring_of_an_owner_is_not_the_owner():
    """Exact after strip + lower — no substring match in either direction."""
    candidates, _ = scan_api_keys(
        _csv("k1,Controller,anthropic,,,",
             'k2,"Controller, Spin State Labs, Finance",anthropic,,,'),
        _agents())
    assert [(c.identifier, c.reason) for c in candidates] == [
        ("k1", REASON_OWNER), ("k2", REASON_OWNER)]


def test_blank_owner_is_surfaced_as_unowned():
    candidates, _ = scan_api_keys(_csv("orphan-batch-key,,openai,2026-07-15,,"), _agents())
    assert [(c.identifier, c.reason) for c in candidates] == [
        ("orphan-batch-key", REASON_UNOWNED)]


def test_unknown_last_used_by_is_surfaced_even_with_an_owner_match():
    candidates, _ = scan_api_keys(
        _csv('reporting-key,"Controller, Spin State Labs",google,,,unknown-runner@example.test'),
        _agents())
    assert [(c.identifier, c.reason) for c in candidates] == [
        ("reporting-key", REASON_LAST_USED_BY)]
    assert candidates[0].evidence["last_used_by"] == "unknown-runner@example.test"


@pytest.mark.parametrize("principal", [
    "invoicing-agent", "INVOICE DRAFTING COPILOT", "controller, spin state labs"])
def test_last_used_by_an_agent_id_name_or_owner_is_known(principal):
    candidates, _ = scan_api_keys(
        _csv(f'k,"Controller, Spin State Labs",anthropic,,,"{principal}"'), _agents())
    assert candidates == []


def test_every_broken_rule_is_named_on_one_candidate():
    candidates, _ = scan_api_keys(_csv("k,,anthropic,,,somebody@example.test"), _agents())
    assert len(candidates) == 1
    assert candidates[0].reason == f"{REASON_UNOWNED}; {REASON_LAST_USED_BY}"


def test_principals_widen_the_known_owners_and_principals():
    rows = _csv("k1,ap.team@example.test,anthropic,,,",
                'k2,"Controller, Spin State Labs",anthropic,,,runner@example.test')
    surfaced, _ = scan_api_keys(rows, _agents())
    assert {c.identifier for c in surfaced} == {"k1", "k2"}
    widened, _ = scan_api_keys(rows, _agents(),
                               known_principals={"AP.Team@example.test", "runner@example.test"})
    assert widened == []


def test_rows_of_only_blank_values_are_not_counted_and_extras_are_ignored():
    """A row with a value but no key_name is REFUSED (D3-R3,
    tests/test_d3_scan_hardening.py); a row of only blanks is not a key."""
    candidates, scanned = scan_api_keys(
        "key_name,owner,service,created,last_used,notes\n"
        ",,,,,\n"
        "k,growth@example.test,x,,,SYNTHETIC note\n", _agents())
    assert scanned == 1 and len(candidates) == 1
    assert "notes" not in candidates[0].evidence


def test_the_fixture_inventory_surfaces_exactly_the_four_shadow_keys():
    text = (FIXTURES / "api-keys.csv").read_text(encoding="utf-8")
    candidates, scanned = scan_api_keys(text, _agents())
    assert scanned == 5
    by_reason = sorted(c.reason for c in candidates)
    assert by_reason == sorted([REASON_OWNER, REASON_UNOWNED, REASON_LAST_USED_BY, REASON_OWNER])
    ids = [c.identifier for c in candidates]
    assert "invoicing-agent-staging" not in ids
    assert "invoicing-agent-prod" in ids
    assert not any("SYNTHETIC" in i for i in ids)  # the pasted key is redacted


@pytest.mark.parametrize("bad, fragment", [
    ("key_name,owner,service,created\nk,o,s,c\n", "missing last_used"),
    ("key_name,ownr,service,created,last_used\nk,o,s,c,l\n", "missing owner"),
    (HEADER + "\nk,Controller, Spin State Labs,s,c,l,\n", "more fields than the header"),
    (HEADER + ",notes\nk,Controller, Spin State Labs,s,,\n", "unquoted comma"),
])
def test_a_malformed_inventory_is_refused_by_name_never_half_read(bad, fragment):
    from agent_registry.redaction import ScanInputError

    with pytest.raises(ScanInputError, match=fragment):
        scan_api_keys(bad, _agents())


def test_a_bom_prefixed_header_is_read():
    candidates, scanned = scan_api_keys("﻿" + _csv("k,,x,,,"), _agents())
    assert scanned == 1 and candidates[0].reason == REASON_UNOWNED


# --- scan_secrets_text: patterns, order, boundaries ----------------------------

@pytest.mark.parametrize("name", sorted(SYNTHETIC))
def test_each_provider_pattern_is_detected(name):
    hits = scan_secrets_text(f"config: {SYNTHETIC[name]}\n")
    assert [h.pattern for h in hits] == [name]


def test_all_patterns_in_one_text_each_counted_once_with_line_numbers():
    text = "\n".join(f"{n} = {v}" for n, v in SYNTHETIC.items())
    hits = scan_secrets_text(text)
    assert [h.pattern for h in hits] == list(SYNTHETIC)
    assert [h.line for h in hits] == list(range(1, len(SYNTHETIC) + 1))


def test_an_anthropic_key_is_not_double_counted_as_the_broad_sk_pattern():
    hits = scan_secrets_text(SYNTHETIC["anthropic"])
    assert [(h.pattern, h.breadth) for h in hits] == [("anthropic", "low")]


def test_breadth_labels_name_the_broad_and_generic_patterns():
    labels = {p.name: p.breadth for p in KEY_PATTERNS}
    assert labels["openai-style-sk"] == "broad"
    assert labels["jwt"] == "generic"
    assert labels["huggingface"] == "moderate"
    assert {labels[n] for n in ("anthropic", "google-api-key", "aws-access-key-id",
                                "github-token", "slack-token", "stripe-secret-key",
                                "google-oauth-access-token")} == {"low"}
    assert [h.breadth for h in scan_secrets_text(SYNTHETIC["openai-style-sk"])] == ["broad"]


@pytest.mark.parametrize("text", [
    "task-" + "a" * 30,                                  # sk- inside a longer word
    "x" + SYNTHETIC["aws-access-key-id"],                # AKIA mid-identifier
    SYNTHETIC["google-api-key"] + "X",                   # 40 chars is not a 39-char key
    SYNTHETIC["aws-access-key-id"] + "Z",                # 21 chars is not a 20-char id
    "sk-" + "ant-" + "short",                            # under the length floor
])
def test_boundaries_and_length_floors(text):
    assert scan_secrets_text(text) == []


def test_the_very_broad_assignment_pattern_ships_off():
    text = "token = " + S + "value123\n"
    assert scan_secrets_text(text) == []
    hits = scan_secrets_text(text, include_very_broad=True)
    assert [(h.pattern, h.breadth) for h in hits] == [("assignment", "very-broad")]
    assert hits[0].length == len(S + "value123")


# --- redaction at the model layer ----------------------------------------------

def test_a_hit_keeps_prefix_7_last_4_and_a_sha256_fingerprint_only():
    raw = SYNTHETIC["anthropic"]
    hit = scan_secrets_text(raw)[0]
    assert hit.redacted == f"{raw[:7]}…{raw[-4:]}"
    assert hit.fingerprint == "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    assert hit.length == len(raw)
    assert raw not in hit.model_dump_json()
    assert "value" not in hit.model_dump()


def test_a_short_value_never_shows_more_than_half():
    raw = SYNTHETIC["aws-access-key-id"]  # 20 characters
    hit = SecretHit(pattern="aws-access-key-id", breadth="low", line=1, value=raw)
    visible = hit.redacted.replace("…", "")
    assert raw.startswith(visible) and len(visible) <= len(raw) // 2


def test_the_raw_value_wins_over_a_redaction_passed_alongside_it():
    raw = SYNTHETIC["huggingface"]
    hit = SecretHit(pattern="huggingface", breadth="moderate", line=1, value=raw,
                    redacted=raw, fingerprint="sha256:0000000000000000")
    assert hit.redacted == f"{raw[:7]}…{raw[-4:]}"
    assert hit.fingerprint == "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def test_a_hit_built_without_value_cannot_carry_a_secret_and_errors_do_not_quote_it():
    """The parse-back path: `redacted` must look like a redaction."""
    from pydantic import ValidationError

    raw = SYNTHETIC["stripe-secret-key"]
    good = SecretHit(pattern="p", breadth="low", line=1, redacted="sk_live…ETIC",
                     fingerprint="sha256:0123456789abcdef", length=len(raw))
    assert good.redacted == "sk_live…ETIC"
    for bad in ({"redacted": raw}, {"redacted": raw[:6] + "…" + raw[6:]},
                {"redacted": "a…b", "fingerprint": raw}):
        fields = {"pattern": "p", "breadth": "low", "line": 1, "length": 3,
                  "redacted": "a…b", "fingerprint": "sha256:0123456789abcdef", **bad}
        with pytest.raises(ValidationError) as exc:
            SecretHit(**fields)
        assert raw not in str(exc.value)
        assert raw[:12] not in str(exc.value)


def test_a_candidate_validation_error_does_not_quote_its_input():
    from pydantic import ValidationError

    raw = SYNTHETIC["anthropic"]
    with pytest.raises(ValidationError) as exc:
        ShadowCandidate(source="api-keys", identifier=raw, display_name=raw,
                        reason="r", evidence={"owner": [raw]})  # a list, not a str
    assert raw not in str(exc.value)
    assert raw[:12] not in str(exc.value)  # not even pydantic's truncated repr


def test_every_candidate_redacts_credential_shaped_strings_it_echoes():
    """The model, not each scanner: an n8n node name carrying a pasted key."""
    raw = SYNTHETIC["github-token"]
    c = ShadowCandidate(source="n8n", identifier=f"wf-{raw}", display_name=raw,
                        reason="r", evidence={"ai_nodes": f"HTTP ({raw})"})
    dumped = c.model_dump_json()
    assert raw not in dumped
    assert "[REDACTED github-token" in c.evidence["ai_nodes"]
    glued = ShadowCandidate(source="service-accounts", identifier="svc_" + raw,
                            display_name="x", reason="r")
    assert raw not in glued.identifier


def test_echoed_strings_redact_even_very_broad_assignments():
    """Scans leave the very-broad pattern off; an ECHO does not — over-redacting
    a report is the safe error."""
    raw = S + "value123"
    c = ShadowCandidate(source="service-accounts", identifier="svc-x", display_name="svc-x",
                        reason="r", evidence={"notes": f"api_key={raw}"})
    assert raw not in c.model_dump_json()
    assert "[REDACTED assignment" in c.evidence["notes"]


@pytest.mark.parametrize("name", [
    "task-runner-automation-agent-01", "desk-booking-automation-workflow",
    "risk-scoring-bot-production-eu"])
def test_redaction_leaves_ordinary_identifiers_readable(name):
    c = ShadowCandidate(source="service-accounts", identifier=name, display_name=name,
                        reason="r", evidence={"owner": name})
    assert (c.identifier, c.display_name, c.evidence["owner"]) == (name, name, name)


# --- /discover ------------------------------------------------------------------

def test_discover_with_only_api_keys_csv_is_200(client):
    r = client.post("/discover", json={"api_keys_csv": (FIXTURES / "api-keys.csv").read_text(encoding="utf-8")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scanned_api_keys"] == 5
    assert body["scanned_workflows"] == 0 and body["scanned_accounts"] == 0
    assert sum(c["reason"] == REASON_OWNER for c in body["candidates"]) == 2


def test_discover_empty_body_is_422(client):
    assert client.post("/discover", json={}).status_code == 422


def test_discover_principals_alone_scan_nothing_and_are_422(client):
    assert client.post("/discover", json={"principals_csv": "owner\nx\n"}).status_code == 422


def test_discover_a_typod_field_is_422_not_an_empty_report(client):
    r = client.post("/discover", json={"api_key_csv": _csv("k,,x,,,")})
    assert r.status_code == 422
    r = client.post("/discover", json={"accounts_csv": "account,type\n", "secret_text": "x"})
    assert r.status_code == 422


def test_discover_raw_values_never_appear_in_the_response(client):
    """Every synthetic value in secrets_text, one pasted as a key's name and one
    in an ignored column: none of them may be in the response body."""
    secrets = "\n".join(SYNTHETIC.values())
    keys = (HEADER + ",notes\n"
            f"{SYNTHETIC['anthropic']},growth@example.test,anthropic,,,,\n"
            f"k2,,x,,,{SYNTHETIC['slack-token']},{SYNTHETIC['stripe-secret-key']}\n")
    r = client.post("/discover", json={"secrets_text": secrets, "api_keys_csv": keys})
    assert r.status_code == 200, r.text
    for raw in SYNTHETIC.values():
        assert raw not in r.text
    body = r.json()
    assert body["scanned_secret_hits"] == len(SYNTHETIC) == len(body["secret_hits"])
    assert {h["pattern"] for h in body["secret_hits"]} == set(SYNTHETIC)
    assert all(set(h) == {"pattern", "breadth", "line", "redacted", "fingerprint", "length"}
               for h in body["secret_hits"])


def test_discover_principals_csv_widens_the_api_key_scan(client):
    keys = _csv("k1,ap.team@example.test,anthropic,,,")
    assert len(client.post("/discover", json={"api_keys_csv": keys}).json()["candidates"]) == 1
    # owners.csv: aliases are ;-separated in their own column
    r = client.post("/discover", json={
        "api_keys_csv": keys,
        "principals_csv": 'owner,aliases\n"Controller, Spin State Labs",AP Lead;ap.team@example.test\n'})
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == []


@pytest.mark.parametrize("field", ["api_keys_csv", "secrets_text", "principals_csv"])
def test_discover_input_over_1_mib_is_422_and_names_the_input(client, field):
    body = {field: "a" * (MAX_SCAN_BYTES + 1)}
    if field == "principals_csv":
        body["secrets_text"] = "nothing here"
    r = client.post("/discover", json=body)
    assert r.status_code == 422
    assert field in r.json()["detail"] and "1 MiB" in r.json()["detail"]


def test_discover_the_cap_counts_utf8_bytes_not_characters(client):
    text = "é" * (MAX_SCAN_BYTES // 2 + 1)  # under the cap in characters, over it in bytes
    assert len(text) < MAX_SCAN_BYTES < len(text.encode("utf-8"))
    r = client.post("/discover", json={"secrets_text": text})
    assert r.status_code == 422 and "1 MiB" in r.json()["detail"]


def test_discover_input_at_exactly_1_mib_is_scanned(client):
    text = "a" * (MAX_SCAN_BYTES - len(SYNTHETIC["anthropic"]) - 1) + " " + SYNTHETIC["anthropic"]
    assert len(text.encode()) == MAX_SCAN_BYTES
    r = client.post("/discover", json={"secrets_text": text})
    assert r.status_code == 200 and r.json()["scanned_secret_hits"] == 1


def test_discover_a_malformed_inventory_is_422_without_echoing_values(client):
    r = client.post("/discover", json={
        "api_keys_csv": HEADER + f"\n{SYNTHETIC['anthropic']},Controller, Spin State Labs,s,c,l,\n"})
    assert r.status_code == 422
    assert "more fields than the header" in r.text
    assert SYNTHETIC["anthropic"] not in r.text


# --- CLI ------------------------------------------------------------------------

def _db_with_agent(tmp_path) -> Path:
    db = tmp_path / "agents.sqlite3"
    store = RegistryStore(db)
    store.add(__import__("agent_registry.models", fromlist=["AgentCreate"]).AgentCreate(
        agent_id="invoicing-agent", name="Invoice Drafting Copilot",
        owner="Controller, Spin State Labs", domain="finance"))
    store.close()
    return db


def test_cli_scan_api_keys_exits_3_on_candidates(tmp_path):
    db = _db_with_agent(tmp_path)
    result = CliRunner().invoke(cli.app, ["scan", "--api-keys", str(FIXTURES / "api-keys.csv"),
                                          "--path", str(db)])
    assert result.exit_code == 3, result.output
    assert REASON_OWNER in result.output
    assert "SYNTHETIC-DO-NOT-USE" not in result.output


def test_cli_scan_api_keys_exits_0_when_every_key_is_owned(tmp_path):
    db = _db_with_agent(tmp_path)
    keys = tmp_path / "keys.csv"
    keys.write_text(_csv('k,"Controller, Spin State Labs",anthropic,,,'), encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["scan", "--api-keys", str(keys), "--path", str(db)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["scanned_api_keys"] == 1


def test_cli_scan_principals_widen_to_exit_0(tmp_path):
    db = _db_with_agent(tmp_path)
    keys = tmp_path / "keys.csv"
    keys.write_text(_csv("k,ap.team@example.test,anthropic,,,"), encoding="utf-8")
    owners = tmp_path / "owners.csv"
    owners.write_text("owner\nap.team@example.test\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli.app, ["scan", "--api-keys", str(keys), "--path", str(db)]).exit_code == 3
    result = runner.invoke(cli.app, ["scan", "--api-keys", str(keys), "--principals", str(owners),
                                     "--path", str(db)])
    assert result.exit_code == 0, result.output


def test_cli_scan_secrets_text_exits_3_and_prints_no_raw_value(tmp_path):
    db = _db_with_agent(tmp_path)
    text = tmp_path / "dump.txt"
    text.write_text("\n".join(SYNTHETIC.values()), encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["scan", "--secrets-text", str(text), "--path", str(db)])
    assert result.exit_code == 3, result.output
    for raw in SYNTHETIC.values():
        assert raw not in result.output
    assert json.loads(result.stdout)["scanned_secret_hits"] == len(SYNTHETIC)


def test_cli_scan_very_broad_is_opt_in(tmp_path):
    db = _db_with_agent(tmp_path)
    text = tmp_path / "env.txt"
    text.write_text("API_KEY=" + S + "value123\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli.app, ["scan", "--secrets-text", str(text), "--path", str(db)]).exit_code == 0
    assert runner.invoke(cli.app, ["scan", "--secrets-text", str(text), "--very-broad",
                                   "--path", str(db)]).exit_code == 3


def test_cli_scan_without_input_or_with_a_malformed_one_exits_2(tmp_path):
    db = _db_with_agent(tmp_path)
    runner = CliRunner()
    assert runner.invoke(cli.app, ["scan", "--path", str(db)]).exit_code == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("key_name,owner\nk,o\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["scan", "--api-keys", str(bad), "--path", str(db)])
    assert result.exit_code == 2
    assert "missing service" in result.output


def test_cli_scan_a_non_utf8_input_exits_2_by_name(tmp_path):
    db = _db_with_agent(tmp_path)
    blob = tmp_path / "export.bin"
    blob.write_bytes(b"key_name,owner\n\xff\xfe\x00k,o\n")
    result = CliRunner().invoke(cli.app, ["scan", "--secrets-text", str(blob), "--path", str(db)])
    assert result.exit_code == 2, result.output
    assert "export.bin is not UTF-8 text" in result.output
