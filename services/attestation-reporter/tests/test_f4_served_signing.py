"""F4 — served attestation signing with the estate key.

When ``FIELD_ATTEST_SIGNER`` and ``FIELD_ATTEST_SIGN_KEY`` are both set and
the key loads, ``GET /pack`` and ``/pack.html`` serve a pack signed under that
name with the provenance ``signed_via: "estate-key"`` INSIDE the signed bytes,
verifiable with ``attest verify --pubkey``; ``/health`` reports ``signing:
on``. Both unset ⇒ the UNSIGNED DRAFT of C4 with no ``signed_via`` key at all
(absent, never null). Exactly one set, a blank name, or a key that does not
load ⇒ still unsigned, the app STARTS, and ``/health`` reports ``signing:
error`` with ``key_error``. The key is loaded once, at app start. Tampering
with a metric or with ``signed_via`` invalidates the served pack; the wrong
public key is named. A pack signed by the PRE-F4 code
(``tests/fixtures/pre_f4``, written with main 53fd921 before this change)
still verifies and reports an unrecorded provenance.

Each test names the guard it pins in its docstring (README "Enforced vs.
Declared"). The ``_stack`` fixture is a copy of the one in
test_attestation_reporter.py (those files stay self-contained).
"""

from __future__ import annotations

import copy
import html as html_module
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import attestation_reporter.api as api_module
import attestation_reporter.signing as signing_module
from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from attestation_reporter.api import create_app
from attestation_reporter.cli import app as cli_app
from attestation_reporter.engine import BoardPack, PackEngine
from attestation_reporter.render import render_html
from attestation_reporter.signing import (
    SIGN_KEY_ENV,
    SIGNER_ENV,
    PackVerificationError,
    parse_pack_json,
    served_signing_from_env,
    sign_pack,
    signed_bytes,
    verify_pack,
)
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.authn import ENV_VAR
from field_core.clients import LedgerClient, RegistryClient
from field_core.signing import canonical_manifest_bytes, generate_keypair, key_fingerprint
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
runner = CliRunner()

#: The D10 signer name, exactly as the estates will set it.
SIGNER = "Don Hagell (custodian, estate key — standing attestation)"
#: The plan's provenance sentence for the HTML footer, verbatim (brief item 5).
ESTATE_SENTENCE = ("Signed via the estate key: the named custodian's standing attestation for served "
                   "packs, not a per-pack human act (v1.2 F4). The quarterly pack of record is the "
                   "CLI-signed one.")
HEALTH_KEYS = {"ok", "service", "version", "build_sha", "signing", "signer", "key_fingerprint"}
ALLOW = "Conformance ALLOW verdicts"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pre_f4"


def _stack(tmp_path: Path) -> SimpleNamespace:
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t"),
    ))
    governor = TestClient(create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3")))
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Inv",
                                   "owner": "AP Lead", "domain": "finance"})
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller", "scope": ["draft invoices"],
        "expires_at": (NOW + timedelta(days=10)).isoformat()})
    for event_type in ("conformance.allow", "conformance.allow", "conformance.allow",
                       "conformance.block", "kill.agent"):
        ledger.post("/events", json={"event_type": event_type, "agent_id": "invoicing-agent",
                                     "payload": {}})
    engine = PackEngine(registry=registry, ledger=ledger, delegation=delegation, governor=governor)
    return SimpleNamespace(engine=engine, registry=registry, ledger=ledger)


def _around_now() -> dict[str, str]:
    return {"since": (NOW - timedelta(days=1)).isoformat(), "until": (NOW + timedelta(days=1)).isoformat()}


def _by_name_raw(pack: dict) -> dict:
    return {m["name"]: m for s in pack["sections"] for m in s["metrics"]}


def _verify(path: Path, body, pubkey: Path):
    """Write ``body`` (a dict or the served text) and run ``attest verify``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if isinstance(body, str) else json.dumps(body, indent=2), encoding="utf-8")
    return runner.invoke(cli_app, ["verify", str(path), "--pubkey", str(pubkey)])


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No perimeter secret and no F4 variables unless a test sets them."""
    for name in (ENV_VAR, SIGNER_ENV, SIGN_KEY_ENV):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def keys(tmp_path):
    """A throwaway estate key pair in the test's temp dir, named as
    ``volume_admin.py keys generate attest-sign`` names them, plus a second
    public key that never signed anything."""
    private_pem, public_pem = generate_keypair()
    _, other_public = generate_keypair()
    d = tmp_path / "attest-keys"
    d.mkdir()
    (d / "attest-sign.pem").write_text(private_pem, encoding="ascii")
    (d / "attest-sign.pub.pem").write_text(public_pem, encoding="ascii")
    (d / "other.pub.pem").write_text(other_public, encoding="ascii")
    return SimpleNamespace(private=private_pem, public=public_pem, other_public=other_public, dir=d,
                           key=d / "attest-sign.pem", pub=d / "attest-sign.pub.pem", other=d / "other.pub.pem")


def _estate_env(monkeypatch, keys, signer: str = SIGNER) -> None:
    monkeypatch.setenv(SIGNER_ENV, signer)
    monkeypatch.setenv(SIGN_KEY_ENV, str(keys.key))


# --- signed with the estate key ------------------------------------------------------------


def test_served_pack_is_signed_by_the_estate_key_and_verifies_with_attest_verify(tmp_path, keys, monkeypatch):
    """Pins the ON branch: both variables set and the key loads ⇒ /health
    signing on with the signer and fingerprint; /pack is signed under the env
    name with signed_via estate-key inside THE BYTES; the served text verifies
    with `attest verify --pubkey` naming the provenance; /pack.html has no
    draft banner and its footer prints the F4 sentence after the fingerprint.
    Delete the `signing.status == "on"` branch in api._build and this fails."""
    s = _stack(tmp_path)
    _estate_env(monkeypatch, keys)
    api = TestClient(create_app(engine=s.engine))

    health = api.get("/health").json()
    assert (health["signing"], health["signer"], health["key_fingerprint"]) == (
        "on", SIGNER, key_fingerprint(keys.public))
    assert set(health) == HEALTH_KEYS and health["ok"] is True  # key_error only in the error state

    window = _around_now()
    r = api.get("/pack", params=window)
    assert r.status_code == 200
    body = r.json()
    assert (body["signed"], body["signer"], body["signed_via"]) == (True, SIGNER, "estate-key")
    assert body["key_fingerprint"] == key_fingerprint(keys.public) and body["signed_at"] and body["signature"]
    served = BoardPack.model_validate(body)  # the wire shape IS the model
    assert served.signed_via == "estate-key"
    # THE BYTES (signing.py) are the served bytes: model dump == raw JSON minus signature
    assert signed_bytes(served) == canonical_manifest_bytes({k: v for k, v in body.items() if k != "signature"})
    assert b'"signed_via":"estate-key"' in signed_bytes(served)
    # the numbers are the engine's, unchanged by signing (served == rendered for the same window)
    rendered = s.engine.build(**window)
    key = lambda m: (m.name, m.value, m.unit, m.status, m.source_query, m.note, m.basis)  # noqa: E731
    assert [key(m) for m in served.all_metrics()] == [key(m) for m in rendered.all_metrics()]
    assert _by_name_raw(body)[ALLOW]["value"] == 3

    # the served text, verified as the raw JSON it is — in-process and through the CLI
    facts = verify_pack(parse_pack_json(r.text), keys.public)
    assert facts == {"signer": SIGNER, "signed_at": body["signed_at"],
                     "key_fingerprint": body["key_fingerprint"], "signed_via": "estate-key"}
    ok = _verify(tmp_path / "served" / "board-pack.json", r.text, keys.pub)
    assert ok.exit_code == 0, ok.output
    assert (f"OK — signature valid: signed by {SIGNER} via estate-key at {body['signed_at']}, "
            f"key {body['key_fingerprint']}") in ok.output

    page = api.get("/pack.html", params=window)
    assert page.status_code == 200
    assert "UNSIGNED DRAFT" not in page.text and "signed: false" not in page.text
    assert "<div class='draft-banner'>" not in page.text  # the element; the CSS class rule is always in <style>
    footer = page.text[page.text.index("<footer>"):page.text.index("</footer>")]
    assert f"Signed by <b>{html_module.escape(SIGNER)}</b>" in footer
    assert ESTATE_SENTENCE in footer and "board-pack.json" in footer
    assert footer.index(body["key_fingerprint"]) < footer.index(ESTATE_SENTENCE)  # after the fingerprint

    # every served window and an org override are signed the same way
    assert api.get("/pack", params={"org": "Acme Corp"}).json()["signed_via"] == "estate-key"
    quarter = api.get("/pack", params={"period": "2026-Q3"}).json()
    assert quarter["signed"] is True and quarter["signer"] == SIGNER
    # the engine is still refused if IT signs: signing is this app's act, never the engine's
    signing = copy.copy(s.engine)
    signing.build = lambda **k: sign_pack(PackEngine.build(s.engine, **k), "Unattended", keys.private)
    refused = TestClient(create_app(engine=signing), raise_server_exceptions=False).get("/pack")
    assert refused.status_code == 500 and "unsigned drafts" in refused.json()["detail"]


def test_tampering_a_served_pack_metric_or_its_provenance_invalidates_it_and_the_wrong_key_is_named(
        tmp_path, keys, monkeypatch):
    """Pins that signed_via is INSIDE the signed bytes: one metric value
    mutated, `estate-key` relabelled `cli`, signed_via removed (passed off as
    a pre-F4 pack) or nulled — each `attest verify` exit 1 naming the failure;
    the wrong public key is exit 1 naming both fingerprints."""
    s = _stack(tmp_path)
    _estate_env(monkeypatch, keys)
    api = TestClient(create_app(engine=s.engine))
    text = api.get("/pack", params=_around_now()).text
    raw = parse_pack_json(text)
    assert raw["signed_via"] == "estate-key"
    assert _verify(tmp_path / "as-served.json", text, keys.pub).exit_code == 0

    metric = copy.deepcopy(raw)
    _by_name_raw(metric)[ALLOW]["value"] += 1
    relabelled = copy.deepcopy(raw)
    relabelled["signed_via"] = "cli"  # an estate-key pack passed off as the pack of record
    removed = copy.deepcopy(raw)
    del removed["signed_via"]  # passed off as a pre-F4 pack
    nulled = copy.deepcopy(raw)
    nulled["signed_via"] = None
    for label, edited in (("metric", metric), ("relabelled", relabelled), ("removed", removed), ("nulled", nulled)):
        assert edited != raw, label
        r = _verify(tmp_path / f"{label}.json", edited, keys.pub)
        assert r.exit_code == 1, (label, r.output)
        assert r.stderr.startswith("FAILED — signature INVALID — board-pack.json was altered after signing"), label
        with pytest.raises(PackVerificationError, match="signature INVALID"):
            verify_pack(edited, keys.public)

    wrong = _verify(tmp_path / "wrong-key.json", text, keys.other)
    assert wrong.exit_code == 1 and "wrong key" in wrong.stderr, wrong.output
    assert raw["key_fingerprint"][:16] in wrong.stderr and key_fingerprint(keys.other_public)[:16] in wrong.stderr


# --- unsigned: unset, misconfigured, unloadable ------------------------------------------------


def test_unset_env_serves_the_unsigned_draft_with_no_signed_via_key(tmp_path, keys, monkeypatch):
    """Pins the OFF branch (both unset, and compose's blank `${VAR:-}`): the
    C4 draft exactly — banner, signed: false, the four signer fields null —
    and `signed_via` ABSENT from the served JSON and from every model dump
    (the additive-compat rule), never null; /health signing off."""
    s = _stack(tmp_path)
    for env in ({}, {SIGNER_ENV: "", SIGN_KEY_ENV: ""}):
        for name in (SIGNER_ENV, SIGN_KEY_ENV):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        api = TestClient(create_app(engine=s.engine))
        health = api.get("/health").json()
        assert (health["signing"], health["signer"], health["key_fingerprint"]) == ("off", None, None), env
        assert set(health) == HEALTH_KEYS, env
        r = api.get("/pack", params=_around_now())
        assert r.status_code == 200
        body = r.json()
        assert body["signed"] is False and "signed_via" not in body, env  # absent, never null
        assert (body["signer"], body["signed_at"], body["key_fingerprint"], body["signature"]) == (
            None, None, None, None)  # the C4 wire shape, nulls kept
        assert _by_name_raw(body)[ALLOW]["value"] == 3
        page = api.get("/pack.html").text
        after_body = page[page.index("<body>") + len("<body>"):].lstrip()
        assert after_body.startswith("<div class='draft-banner'>UNSIGNED DRAFT") and "signed: false" in page
        assert "Signed via" not in page
        nothing = _verify(tmp_path / "unsigned.json", r.text, keys.pub)
        assert nothing.exit_code == 1 and "nothing to verify" in nothing.stderr

    unsigned = s.engine.build(now=NOW)
    assert unsigned.signed_via is None
    for dump in (unsigned.model_dump(), unsigned.model_dump(mode="json"), json.loads(unsigned.model_dump_json()),
                 unsigned.model_dump(mode="json", exclude={"signature"})):
        assert "signed_via" not in dump
    assert json.loads(unsigned.model_dump_json())["signature"] is None  # other absent fields keep their null
    assert served_signing_from_env({}).status == "off"


def test_one_of_two_set_stays_unsigned_and_health_names_the_misconfiguration(tmp_path, keys, monkeypatch):
    """Pins the two refusals in served_signing_from_env: a signer without a key
    (never sign without a key) and a key without a signer, or under a blank
    name (never sign under a blank name) ⇒ unsigned drafts, signing "error",
    key_error naming the missing variable. Delete either branch and the pack
    would be signed (or the app would raise) and this fails."""
    s = _stack(tmp_path)
    key = str(keys.key)
    cases = [
        ({SIGNER_ENV: SIGNER}, "FIELD_ATTEST_SIGNER is set but FIELD_ATTEST_SIGN_KEY is not"),
        ({SIGNER_ENV: SIGNER, SIGN_KEY_ENV: "   "}, "FIELD_ATTEST_SIGNER is set but FIELD_ATTEST_SIGN_KEY is not"),
        ({SIGN_KEY_ENV: key}, "FIELD_ATTEST_SIGN_KEY is set but FIELD_ATTEST_SIGNER is unset or blank"),
        ({SIGNER_ENV: "   ", SIGN_KEY_ENV: key}, "FIELD_ATTEST_SIGN_KEY is set but FIELD_ATTEST_SIGNER is unset or blank"),
    ]
    for env, reason in cases:
        for name in (SIGNER_ENV, SIGN_KEY_ENV):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        api = TestClient(create_app(engine=s.engine))  # returns: a misconfiguration is never an exit
        health = api.get("/health").json()
        assert health["signing"] == "error", env
        assert health["key_error"].startswith(reason) and "stay UNSIGNED" in health["key_error"], env
        assert (health["signer"], health["key_fingerprint"]) == (None, None)
        assert set(health) == HEALTH_KEYS | {"key_error"}
        body = api.get("/pack").json()
        assert body["signed"] is False and "signed_via" not in body and body["signature"] is None, env
        assert "UNSIGNED DRAFT" in api.get("/pack.html").text
        state = served_signing_from_env(env)  # the same decision from a plain mapping
        assert (state.status, state.signer, state.private_key_pem) == ("error", None, None)


def _bad_keys(d: Path, public_pem: str) -> dict[str, Path]:
    d.mkdir(parents=True)
    bad = {name: d / f"{name}.pem" for name in ("missing", "garbage", "empty", "public-key", "not-ed25519", "encrypted")}
    bad["directory"] = d / "a-directory"
    bad["directory"].mkdir()
    bad["garbage"].write_text("-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n")
    bad["empty"].write_text("")
    bad["public-key"].write_text(public_pem)
    pkcs8 = serialization.PrivateFormat.PKCS8
    bad["not-ed25519"].write_bytes(ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, pkcs8, serialization.NoEncryption()))
    bad["encrypted"].write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, pkcs8, serialization.BestAvailableEncryption(b"pw")))
    return bad


def test_an_unloadable_key_starts_the_app_unsigned_with_health_error(tmp_path, keys, monkeypatch):
    """Pins the fail-open-UNSIGNED branch: seven keys that do not load
    (missing, a directory, garbage, empty, a public key, not Ed25519,
    encrypted) ⇒ create_app RETURNS (never a process exit), /health signing
    "error" with a short key_error naming the failure and never key material
    nor the configured path (/health is open: the file's name only), /pack
    unsigned with no signed_via, the banner on /pack.html. Delete the except
    in served_signing_from_env and create_app raises here."""
    s = _stack(tmp_path)
    monkeypatch.setenv(SIGNER_ENV, SIGNER)
    for label, path in _bad_keys(tmp_path / "bad", keys.public).items():
        monkeypatch.setenv(SIGN_KEY_ENV, str(path))
        api = TestClient(create_app(engine=s.engine))
        health = api.get("/health").json()
        assert health["signing"] == "error", label
        error = health["key_error"]
        assert error.startswith("FIELD_ATTEST_SIGN_KEY did not load — signing key") and error.endswith(
            ": served packs stay UNSIGNED"), (label, error)
        assert "BEGIN" not in error and "not a key" not in error and len(error) < 300, label
        assert str(tmp_path) not in error, (label, error)  # the open route never prints the configured path
        if label in ("missing", "directory"):  # the read failures name the file — by its name only
            assert path.name in error and str(path.parent) not in error, (label, error)
        assert (health["signer"], health["key_fingerprint"]) == (None, None)
        assert set(health) == HEALTH_KEYS | {"key_error"}
        body = api.get("/pack").json()
        assert body["signed"] is False and "signed_via" not in body, label
        assert "UNSIGNED DRAFT" in api.get("/pack.html").text
        assert "PRIVATE" not in repr(api.app.state.signing)


def test_the_key_is_loaded_once_at_app_start_not_per_request(tmp_path, keys, monkeypatch):
    """Pins load-once: one load_signing_key call for any number of requests;
    the state captured at start outlives the file and the environment; a new
    app over the missing file starts unsigned with the error named; the PEM
    is never in the state's repr."""
    s = _stack(tmp_path)
    loads: list[str] = []
    real = signing_module.load_signing_key

    def counting(path):
        loads.append(str(path))
        return real(path)

    monkeypatch.setattr(signing_module, "load_signing_key", counting)
    _estate_env(monkeypatch, keys)
    api = TestClient(create_app(engine=s.engine))
    assert loads == [str(keys.key)]
    for _ in range(3):
        assert api.get("/pack").json()["signed_via"] == "estate-key"
    assert api.get("/pack.html").status_code == 200
    assert loads == [str(keys.key)]  # once, at start

    keys.key.unlink()
    monkeypatch.delenv(SIGNER_ENV)
    monkeypatch.delenv(SIGN_KEY_ENV)
    body = api.get("/pack").json()
    assert body["signed"] is True and body["signer"] == SIGNER and body["signed_via"] == "estate-key"
    assert api.get("/health").json()["signing"] == "on"
    assert loads == [str(keys.key)]
    assert "PRIVATE" not in repr(api.app.state.signing) and "PRIVATE" not in str(api.app.state.signing)

    _estate_env(monkeypatch, keys)  # the same env, but the key file is gone
    fresh = TestClient(create_app(engine=s.engine))
    assert fresh.get("/health").json()["signing"] == "error"
    assert fresh.get("/pack").json()["signed"] is False
    assert loads == [str(keys.key)] * 2


# --- compatibility: the bytes before and after F4 -----------------------------------------------


def test_a_pack_signed_before_f4_still_verifies_and_its_provenance_is_unrecorded():
    """The compatibility trap (brief item 3): ``tests/fixtures/pre_f4/board-pack.json``
    was signed by the PRE-F4 ``sign_pack`` (main 53fd921, generated before this
    change; only its public key is kept). It has no ``signed_via`` key. It
    still verifies — in-process and through the CLI, which names the
    provenance as unrecorded — and the NEW model dumps it to exactly the bytes
    it was signed over (signed_via omitted, never null). Nobody can retro-label
    it: adding signed_via (either value, or null) invalidates it."""
    text = (FIXTURE / "board-pack.json").read_text(encoding="utf-8")
    public = (FIXTURE / "signer.pub.pem").read_text(encoding="ascii")
    raw = parse_pack_json(text)
    assert raw["signed"] is True and "signed_via" not in text
    facts = verify_pack(raw, public)
    assert facts["signer"] == "Don Hagell (pre-F4 fixture)" and facts["signed_via"] is None

    model = BoardPack.model_validate(raw)
    assert model.signed and model.signed_via is None
    assert signed_bytes(model) == canonical_manifest_bytes({k: v for k, v in raw.items() if k != "signature"})
    assert json.loads(model.model_dump_json()) == raw  # the new model reproduces the old file exactly
    page = render_html(model)
    assert "Signing provenance not recorded (signed before v1.2 F4)" in page and "Signed via" not in page
    assert "UNSIGNED DRAFT" not in page and facts["key_fingerprint"] in page

    ok = runner.invoke(cli_app, ["verify", str(FIXTURE / "board-pack.json"), "--pubkey", str(FIXTURE / "signer.pub.pem")])
    assert ok.exit_code == 0, ok.output
    assert ("signed by Don Hagell (pre-F4 fixture) via an unrecorded path (signed before v1.2 F4: "
            "no signed_via) at") in ok.output

    for value in ("cli", "estate-key", None):
        with pytest.raises(PackVerificationError, match="signature INVALID"):
            verify_pack({**raw, "signed_via": value}, public)


def test_cli_render_records_signed_via_cli_and_the_footer_names_the_cli_path(tmp_path, keys, monkeypatch):
    """The CLI path records signed_via "cli" (verify names it; the footer
    names the CLI, not the estate sentence). The F4 variables are the
    SERVER's: set, they change nothing about `attest render` — an unsigned
    render stays an unsigned draft with no signed_via. sign_pack refuses any
    provenance but the two."""
    s = _stack(tmp_path)
    monkeypatch.setattr(api_module, "engine_from_env", lambda org="Spin State Labs": s.engine)
    _estate_env(monkeypatch, keys)  # present, and irrelevant to the CLI
    out = tmp_path / "cli"
    r = runner.invoke(cli_app, ["render", "--out", str(out), "--no-pdf", "--period", "2026-Q3",
                                "--signer", "Don Hagell", "--sign-key", str(keys.key)])
    assert r.exit_code == 0 and "signed by Don Hagell via cli" in r.output, r.output
    raw = parse_pack_json((out / "board-pack.json").read_text(encoding="utf-8"))
    assert (raw["signed_via"], raw["signer"]) == ("cli", "Don Hagell")
    ok = runner.invoke(cli_app, ["verify", str(out / "board-pack.json"), "--pubkey", str(keys.pub)])
    assert ok.exit_code == 0 and "signed by Don Hagell via cli at" in ok.output, ok.output
    page = (out / "board-pack.html").read_text(encoding="utf-8")
    assert "Signed via the CLI (attest render --signer --sign-key)" in page and ESTATE_SENTENCE not in page

    r = runner.invoke(cli_app, ["render", "--out", str(tmp_path / "cli-unsigned"), "--no-pdf", "--period", "2026-Q3"])
    assert r.exit_code == 0 and "UNSIGNED DRAFT" in r.output, r.output
    raw = parse_pack_json((tmp_path / "cli-unsigned" / "board-pack.json").read_text(encoding="utf-8"))
    assert raw["signed"] is False and "signed_via" not in raw

    unsigned = s.engine.build(now=NOW)
    for bad in ("server", "CLI", "", None):
        with pytest.raises(ValueError, match="signed_via"):
            sign_pack(unsigned, "Don Hagell", keys.private, signed_via=bad)
    estate = sign_pack(unsigned, SIGNER, keys.private, signed_via="estate-key")
    assert estate.signed_via == "estate-key"
    assert verify_pack(json.loads(estate.model_dump_json()), keys.public)["signed_via"] == "estate-key"
    assert sign_pack(unsigned, "Don Hagell", keys.private).signed_via == "cli"  # the default is the CLI path


def test_signed_via_is_optional_on_a_signed_pack_and_refused_on_an_unsigned_one(keys):
    """The model rules behind the shapes above: a signed pack may carry no
    signed_via (pre-F4) or one of the two values; an unsigned pack may not
    carry one; any other value is refused."""
    unsigned = PackEngine().build(now=NOW)  # no upstreams: offline, every metric unavailable
    dump = json.loads(unsigned.model_dump_json())
    assert "signed_via" not in dump
    for value in ("cli", "estate-key"):
        with pytest.raises(ValueError, match="signed_via"):
            BoardPack.model_validate({**dump, "signed_via": value})
    signed = json.loads(sign_pack(unsigned, "Don Hagell", keys.private).model_dump_json())
    assert signed["signed_via"] == "cli"
    assert BoardPack.model_validate({k: v for k, v in signed.items() if k != "signed_via"}).signed_via is None
    assert BoardPack.model_validate({**signed, "signed_via": None}).signed_via is None
    assert BoardPack.model_validate({**signed, "signed_via": "estate-key"}).signed_via == "estate-key"
    with pytest.raises(ValueError):
        BoardPack.model_validate({**signed, "signed_via": "server"})
