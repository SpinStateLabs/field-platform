"""D5 — contract keys are validated as Ed25519 on write, CLI and API alike.

``fedbroker add-contract --pubkey`` validates the PEM up front (exit 1, no
request made); the same validator sits on
``FederationContract.counterparty_pubkey_pem``, so a raw PUT with a bad key
is a 422. Every key here is generated per test or is obviously-synthetic
garbage text; none is real.
"""

import json
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from federation_broker import cli as cli_mod
from federation_broker.api import create_app
from federation_broker.engine import (
    BrokerEngine,
    ContractStore,
    FederationContract,
    ed25519_public_pem_error,
)
from field_core.signing import generate_keypair
from field_core.templates_api import template_data

HOME = "Spin State Labs"
COUNTERPARTY = "Borealis Example Corp"
SCOPE = "exchange invoice status"
DATA_CLASS = "invoice metadata"

SYNTHETIC_GARBAGE_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "U1lOVEhFVElDLU5PVC1BLUtFWS1TWU5USEVUSUMtTk9ULUEtS0VZ\n"
    "-----END PUBLIC KEY-----\n"
)


def x25519_public_pem() -> str:
    """A well-formed PEM public key of the WRONG type (X25519, also 32 bytes)."""
    return X25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def bad_keys() -> dict[str, str]:
    ed_private, ed_public = generate_keypair()  # generated per test, never persisted
    return {
        "garbage-text": "SYNTHETIC not a pem at all",
        "garbage-pem-block": SYNTHETIC_GARBAGE_PEM,
        "private-key-pem": ed_private,
        "x25519-public-pem": x25519_public_pem(),
        "truncated": generate_keypair()[1][:40],
        "blank": "   ",
        "non-ascii": "-----BEGIN PUBLIC KEY-----\nSYNTHÉTIQUE\n-----END PUBLIC KEY-----\n",
        # A valid public block is not enough: the loader reads only the FIRST
        # block, so anything riding along would be stored and served back.
        "public-then-private": ed_public + ed_private,  # `cat public.pem private.pem`
        "public-then-trailing-text": ed_public + "\nSYNTHETIC-API-KEY=synthetic-not-real\n",
        "leading-text-then-public": "note: synthetic\n" + ed_public,
        "two-public-keys": ed_public + generate_keypair()[1],
    }


def key_material(value: str) -> list[str]:
    """The lines of ``value`` that would be a leak if quoted back (armor
    lines and blanks aside)."""
    return [line.strip() for line in value.splitlines()
            if line.strip() and not line.strip().startswith("-----")]


def counterparty_manifest():
    data = template_data("client-facing-agent")
    data["agent"]["name"] = "borealis-billing-agent"
    data["identity"].update(principal="VP Finance, Borealis (demo)", org=COUNTERPARTY,
                            jurisdiction=["PIPEDA"], model_provider="Anthropic")
    data["enforcement"]["kill_switch"].update(endpoint="https://borealis.example/kill",
                                              method="HTTP POST")
    data["ledger"]["store"] = "borealis WORM store (demo)"
    data["delegation"].update(granted_by="VP Finance, Borealis (demo)", scope=[SCOPE])
    data["delegation"]["revocation"] = {"method": "HTTP POST",
                                        "endpoint": "https://borealis.example/revoke"}
    data["federated"] = {
        "isolated": False,
        "allowed_peers": [{"agent_id": "invoicing-agent", "org": HOME,
                           "trust_basis": "federation contract FED-2026-001 (demo)"}],
        "contracts": [{"peer": "invoicing-agent", "contract_ref": "FED-2026-001",
                       "scope": SCOPE}],
    }
    return data


@pytest.fixture()
def broker(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", HOME)
    return TestClient(create_app(engine=BrokerEngine(
        store=ContractStore(tmp_path / "contracts.sqlite3"))))


def contract_body(**overrides):
    body = {"contract_id": "FED-2026-001", "counterparty_org": COUNTERPARTY,
            "allowed_scopes": [SCOPE], "allowed_data_classes": [DATA_CLASS],
            "active": True}
    body.update(overrides)
    return body


# --- the validator itself ---------------------------------------------------

def test_validator_accepts_a_real_ed25519_public_key():
    _, public_pem = generate_keypair()
    assert ed25519_public_pem_error(public_pem) is None


@pytest.mark.parametrize("name", sorted(bad_keys()))
def test_validator_refuses_everything_else(name):
    error = ed25519_public_pem_error(bad_keys()[name])
    assert error
    # a blank key says "omit it" rather than a loader error
    assert ("empty" in error) is (name == "blank")


# --- API / model: raw PUTs --------------------------------------------------

@pytest.mark.parametrize("name", sorted(bad_keys()))
def test_raw_put_with_a_bad_key_is_422_and_stores_nothing(broker, name):
    sent = bad_keys()[name]
    r = broker.put("/contracts/FED-2026-001",
                   json=contract_body(counterparty_pubkey_pem=sent))
    assert r.status_code == 422, r.status_code
    assert "counterparty_pubkey_pem" in r.text
    assert broker.get("/contracts").json() == []
    for line in key_material(sent):
        assert line not in r.text  # the 422 never quotes the key back


def test_public_key_with_private_key_appended_is_never_stored_sent_or_echoed(cli):
    """``cat public.pem private.pem`` — a valid first block with a PRIVATE
    key after it — is refused on every path, and the private key is never
    quoted, stored, listed or sent."""
    private_pem, public_pem = generate_keypair()  # generated here, never persisted
    both = public_pem + private_pem
    secret_lines = key_material(private_pem)
    assert secret_lines

    r = cli.broker.put("/contracts/FED-2026-001",
                       json=contract_body(counterparty_pubkey_pem=both))
    assert r.status_code == 422, r.status_code
    listed = cli.broker.get("/contracts")
    assert listed.json() == []
    for line in secret_lines:
        assert line not in r.text
        assert line not in listed.text

    result = cli.run("add-contract", "FED-2026-001", "--org", COUNTERPARTY,
                     "--scope", SCOPE, "--data-class", DATA_CLASS, "--pubkey", both)
    assert result.exit_code == 1
    assert "private-key material" in result.output
    assert cli.calls == []
    for line in secret_lines:
        assert line not in result.output


def test_a_422_never_quotes_the_request_body(broker):
    """FastAPI's default 422 quotes each error's ``input``; a ``missing``
    error quotes the WHOLE body — here a pasted private key that is not
    even the field in error."""
    private_pem, _ = generate_keypair()
    body = contract_body(counterparty_pubkey_pem=private_pem)
    del body["allowed_scopes"]
    r = broker.put("/contracts/FED-2026-001", json=body)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert {tuple(e["loc"]) for e in detail} >= {("body", "allowed_scopes"),
                                                ("body", "counterparty_pubkey_pem")}
    assert all("input" not in e and e["msg"] for e in detail)
    for line in key_material(private_pem):
        assert line not in r.text


@pytest.mark.parametrize("variant", ["crlf", "surrounding-whitespace", "indented",
                                     "rewrapped"])
def test_whitespace_variants_of_one_key_are_accepted_and_stored_canonical(broker, variant):
    """Only whitespace may differ from the canonical PEM; what is stored and
    listed is the canonical SubjectPublicKeyInfo PEM."""
    _, public_pem = generate_keypair()
    header, body, footer = public_pem.strip().splitlines()
    sent = {
        "crlf": public_pem.replace("\n", "\r\n"),
        "surrounding-whitespace": "\n  " + public_pem + "\n\n",
        "indented": "\n".join("    " + line for line in public_pem.splitlines()),
        "rewrapped": "\n".join([header, body[:30], body[30:], footer]),
    }[variant]
    assert sent != public_pem
    assert ed25519_public_pem_error(sent) is None
    r = broker.put("/contracts/FED-2026-001",
                   json=contract_body(counterparty_pubkey_pem=sent))
    assert r.status_code == 200, r.text
    assert r.json()["counterparty_pubkey_pem"] == public_pem
    assert broker.get("/contracts").json()[0]["counterparty_pubkey_pem"] == public_pem


def test_raw_put_with_a_real_key_is_stored_and_listed(broker):
    _, public_pem = generate_keypair()
    r = broker.put("/contracts/FED-2026-001",
                   json=contract_body(counterparty_pubkey_pem=public_pem))
    assert r.status_code == 200, r.text
    assert broker.get("/contracts").json()[0]["counterparty_pubkey_pem"] == public_pem


def test_model_refuses_a_bad_key_outside_the_api():
    with pytest.raises(ValueError, match="Ed25519"):
        FederationContract(**contract_body(counterparty_pubkey_pem=SYNTHETIC_GARBAGE_PEM))


def test_legacy_row_with_unusable_key_still_lists_and_fails_closed(broker):
    """A row written before write-time validation (simulated with
    ``model_construct``, which skips validators) must not break
    ``GET /contracts``, and its inbound crossings BLOCK — never keyless."""
    store = broker.app.state.engine.store
    store.save(FederationContract.model_construct(
        **contract_body(contract_ref=None, counterparty_pubkey_pem=SYNTHETIC_GARBAGE_PEM)))

    listed = broker.get("/contracts")
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["counterparty_pubkey_pem"] == SYNTHETIC_GARBAGE_PEM

    verdict = broker.post("/crossing", json={
        "counterparty_org": COUNTERPARTY, "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": counterparty_manifest(),
        "manifest_signature": "U1lOVEhFVElD",  # synthetic, never a real signature
        "scope": SCOPE, "data_class": DATA_CLASS,
    }).json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.peer"
    assert "unusable key" in verdict["reasons"][0]


def test_legacy_row_with_empty_key_is_not_waved_through_keyless(broker):
    store = broker.app.state.engine.store
    store.save(FederationContract.model_construct(
        **contract_body(contract_ref=None, counterparty_pubkey_pem="")))
    verdict = broker.post("/crossing", json={
        "counterparty_org": COUNTERPARTY, "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": counterparty_manifest(),
        "scope": SCOPE, "data_class": DATA_CLASS,
    }).json()
    assert verdict["decision"] == "BLOCK"
    assert "unusable key" in verdict["reasons"][0]


def test_legacy_row_holding_private_key_material_lists_withheld_and_fails_closed(broker):
    """A row stored before write-time validation may hold a pasted private
    key. It still lists, but the key text is withheld — not served to anyone
    who lists contracts — and its inbound crossings still BLOCK (the
    withheld value is never mistaken for keyless)."""
    private_pem, public_pem = generate_keypair()  # generated here, never persisted
    store = broker.app.state.engine.store
    store.save(FederationContract.model_construct(
        **contract_body(contract_ref=None, counterparty_pubkey_pem=public_pem + private_pem)))

    listed = broker.get("/contracts")
    assert listed.status_code == 200, listed.status_code
    row = listed.json()[0]
    assert row["counterparty_pubkey_pem"] is not None
    assert "withheld" in row["counterparty_pubkey_pem"]
    assert "BEGIN PRIVATE KEY" not in listed.text
    for line in key_material(private_pem):
        assert line not in listed.text

    verdict = broker.post("/crossing", json={
        "counterparty_org": COUNTERPARTY, "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": counterparty_manifest(),
        "scope": SCOPE, "data_class": DATA_CLASS,
    })
    assert verdict.json()["decision"] == "BLOCK"
    assert "unusable key" in verdict.json()["reasons"][0]
    for line in key_material(private_pem):
        assert line not in verdict.text


def test_model_error_outside_the_api_does_not_quote_the_key():
    from pydantic import ValidationError

    private_pem, public_pem = generate_keypair()
    with pytest.raises(ValidationError) as caught:
        FederationContract(**contract_body(counterparty_pubkey_pem=public_pem + private_pem))
    text = str(caught.value)
    assert "private-key material" in text
    assert "input_value" not in text
    assert "PRIVATE KEY-----" not in text and "PUBLIC KEY-----" not in text


# --- CLI --------------------------------------------------------------------

class RoutedHttpx:
    """Stands in for the ``httpx`` module inside ``federation_broker.cli``:
    same calls, routed to the in-process broker, and every call recorded."""

    def __init__(self, client):
        self.client = client
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[object] = []

    def _route(self, verb):
        def call(url, **kwargs):
            self.calls.append((verb, url))
            self.bodies.append(kwargs.get("json"))
            kwargs.pop("timeout", None)
            return getattr(self.client, verb)(url, **kwargs)
        return call

    def __getattr__(self, verb):
        if verb in {"get", "put", "post"}:
            return self._route(verb)
        raise AttributeError(verb)


@pytest.fixture()
def cli(broker, monkeypatch):
    routed = RoutedHttpx(broker)
    monkeypatch.setattr(cli_mod, "httpx", routed)
    monkeypatch.setenv("FIELD_FEDERATION_URL", "http://testserver")
    runner = CliRunner()

    def run(*args):
        return runner.invoke(cli_mod.app, list(args))

    return SimpleNamespace(run=run, calls=routed.calls, bodies=routed.bodies, broker=broker)


def write_manifest(tmp_path, data):
    import yaml

    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_cli_add_contract_pubkey_registers_key_then_unsigned_crossing_blocks(cli, tmp_path):
    keys = cli.run("keygen", "--out-dir", str(tmp_path), "--name", "synthetic-borealis")
    assert keys.exit_code == 0, keys.output
    public_file = tmp_path / "synthetic-borealis-public.pem"
    private_file = tmp_path / "synthetic-borealis-private.pem"

    added = cli.run("add-contract", "FED-2026-001", "--org", COUNTERPARTY,
                    "--scope", SCOPE, "--data-class", DATA_CLASS,
                    "--pubkey", str(public_file))
    assert added.exit_code == 0, added.output
    stored = cli.broker.get("/contracts").json()
    assert stored[0]["counterparty_pubkey_pem"] == public_file.read_text(encoding="ascii")

    manifest = write_manifest(tmp_path, counterparty_manifest())
    unsigned = cli.run("crossing", "--org", COUNTERPARTY,
                       "--agent-id", "borealis-billing-agent", "--manifest", str(manifest),
                       "--scope", SCOPE, "--data-class", DATA_CLASS)
    assert unsigned.exit_code == 1, unsigned.output
    assert "requires a signed manifest" in unsigned.output

    signature = cli.run("sign", "--manifest", str(manifest), "--key", str(private_file))
    assert signature.exit_code == 0, signature.output
    signed = cli.run("crossing", "--org", COUNTERPARTY,
                     "--agent-id", "borealis-billing-agent", "--manifest", str(manifest),
                     "--scope", SCOPE, "--data-class", DATA_CLASS,
                     "--signature", signature.output.strip())
    assert signed.exit_code == 0, signed.output
    assert json.loads(signed.output)["decision"] == "ALLOW"


def test_cli_add_contract_accepts_inline_pem_text(cli):
    _, public_pem = generate_keypair()
    added = cli.run("add-contract", "FED-2026-001", "--org", COUNTERPARTY,
                    "--scope", SCOPE, "--data-class", DATA_CLASS, "--pubkey", public_pem)
    assert added.exit_code == 0, added.output
    assert cli.broker.get("/contracts").json()[0]["counterparty_pubkey_pem"] == public_pem


def test_cli_sends_only_the_canonical_pem(cli):
    """The CLI sends the key's canonical PEM, not the text it was given."""
    _, public_pem = generate_keypair()
    added = cli.run("add-contract", "FED-2026-001", "--org", COUNTERPARTY,
                    "--scope", SCOPE, "--data-class", DATA_CLASS,
                    "--pubkey", "  " + public_pem.replace("\n", "\r\n") + "\r\n")
    assert added.exit_code == 0, added.output
    assert [body["counterparty_pubkey_pem"] for body in cli.bodies] == [public_pem]


@pytest.mark.parametrize("name", sorted(bad_keys()) + ["missing-file"])
def test_cli_add_contract_bad_pubkey_exits_1_before_any_request(cli, tmp_path, name):
    content = ""
    if name == "missing-file":
        value = str(tmp_path / "no-such-key.pem")
    else:
        content = bad_keys()[name]
        key_file = tmp_path / f"{name}.pem"
        key_file.write_bytes(content.encode("utf-8"))
        value = str(key_file)
    result = cli.run("add-contract", "FED-2026-001", "--org", COUNTERPARTY,
                     "--scope", SCOPE, "--data-class", DATA_CLASS, "--pubkey", value)
    assert result.exit_code == 1, result.output
    assert "--pubkey" in result.output
    assert cli.calls == []  # validated up front: nothing was sent
    assert cli.broker.get("/contracts").json() == []
    if content.strip():
        body = content.strip().splitlines()[min(1, len(content.strip().splitlines()) - 1)]
        assert body not in result.output  # key material is never echoed
    for line in key_material(content):
        assert line not in result.output


def test_cli_inline_private_key_is_refused_and_never_echoed(cli):
    private_pem, _ = generate_keypair()  # generated here, never persisted
    result = cli.run("add-contract", "FED-2026-001", "--org", COUNTERPARTY,
                     "--scope", SCOPE, "--data-class", DATA_CLASS, "--pubkey", private_pem)
    assert result.exit_code == 1, result.output
    assert private_pem.splitlines()[1] not in result.output
    assert cli.calls == []


def test_cli_crossing_outbound_direction(cli, tmp_path):
    assert cli.run("add-contract", "FED-2026-001", "--org", COUNTERPARTY,
                   "--scope", SCOPE, "--data-class", DATA_CLASS).exit_code == 0
    ours = counterparty_manifest()
    ours["agent"]["name"] = "invoicing-agent"
    ours["identity"]["org"] = HOME
    ours["federated"]["allowed_peers"][0]["org"] = COUNTERPARTY
    manifest = write_manifest(tmp_path, ours)
    result = cli.run("crossing", "--direction", "outbound", "--org", COUNTERPARTY,
                     "--agent-id", "invoicing-agent", "--manifest", str(manifest),
                     "--scope", SCOPE, "--data-class", DATA_CLASS)
    assert result.exit_code == 0, result.output
    verdict = json.loads(result.output)
    assert verdict["context"]["direction"] == "outbound"
    assert verdict["agent_id"] == f"{HOME}/invoicing-agent"

    over = cli.run("crossing", "--direction", "outbound", "--org", COUNTERPARTY,
                   "--agent-id", "invoicing-agent", "--manifest", str(manifest),
                   "--scope", SCOPE, "--data-class", "customer PII")
    assert over.exit_code == 1, over.output
