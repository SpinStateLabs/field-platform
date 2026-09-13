"""X1b — `delegation doa check`: the pre-arm dry run of the DOA mint gate.

For a registered, ACTIVE agent whose registry manifest_ref is the
`--manifest-ref` given, the verb must say exactly what the mint route would
say, and it must never mint, write or connect. The verb does not read the
registry: an unregistered (404) or killed (409) agent, or a record whose
manifest_ref differs from the one passed, is outside this agreement (README
LIMITS). Both halves are pinned here:

* every refusal clause, and ALLOW, is driven through BOTH the real route (over
  TestClient, with a real registry and ledger) and the verb (in-process, with
  the same roster and manifest files), and the two must agree on outcome,
  clause id and message — character for character;
* the verb runs with every real client, the token store and httpx made to
  explode, from an empty working directory, and must still answer and leave
  nothing behind;
* the verb never prints ALLOW unless the route actually ran the roster gate,
  and it restores `FIELD_DOA_ROSTER` exactly as it found it.
* a RELATIVE manifest_ref is passed to the route's resolver verbatim, so it
  resolves against FIELD_MANIFEST_DIR in both, never against the verb's CWD.

Helpers are copied (not imported) from test_doa_roster.py so the two files
stay independent; that suite is unmodified.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.cli import app as cli_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.store import TokenStore
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

AGENT_ID = "invoicing-agent"
GRANTOR = "Don Hagell, Spin State Labs"
MANIFEST_SCOPE = ["read timesheets", "draft invoices", "send invoice email"]
LINE = re.compile(r"^REFUSED(?: (?P<clause>\S+))? \((?P<status>\d{3})\): (?P<message>.*)$", re.S)


def write_manifest(directory: Path, valid: bool = True) -> Path:
    path = directory / "agent-manifest.yaml"
    if not valid:
        path.write_text("delegation: [this is: not a manifest\n", encoding="utf-8")
        return path
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["identity"]["principal"] = GRANTOR
    data["delegation"]["granted_by"] = GRANTOR
    data["delegation"]["scope"] = list(MANIFEST_SCOPE)
    data["delegation"]["expiry"] = "2027-06-30"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def write_roster(directory: Path, **overrides) -> Path:
    row = {
        "grantor": GRANTOR,
        "allowed_scope": list(MANIFEST_SCOPE),
        "max_ttl_days": 30,
        "max_spend_usd": 500.0,
        "active": True,
    }
    row.update(overrides)
    path = directory / "doa-roster.yaml"
    path.write_text(yaml.safe_dump({"grantors": [row]}, sort_keys=False), encoding="utf-8")
    return path


class Route:
    """The real mint route: registry + ledger + delegation, over TestClient."""

    def __init__(self, tmp_path: Path, manifest_ref: Path | None):
        self.ledger_store = LedgerStore(tmp_path / "events.jsonl")
        registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
        self.ledger = TestClient(create_ledger_app(store=self.ledger_store))
        self.delegation = TestClient(create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t"),
            registry=RegistryClient(client=registry, base_url="http://t"),
        ))
        body = {"agent_id": AGENT_ID, "name": "Invoicing", "owner": GRANTOR, "domain": "finance"}
        if manifest_ref is not None:
            body["manifest_ref"] = str(manifest_ref)
        assert registry.post("/agents", json=body).status_code == 201

    def mint(self, grantor: str, scope: list[str], ttl_days: int) -> tuple[str, str | None, str]:
        r = self.delegation.post("/tokens", json={
            "agent_id": AGENT_ID, "granted_by": grantor, "scope": scope,
            "ttl_seconds": ttl_days * 86400,
        })
        if r.status_code == 201:
            return ("ALLOW", None, "")
        detail = r.json()["detail"]
        if isinstance(detail, dict):
            return (str(r.status_code), detail["clause_id"], detail["message"])
        return (str(r.status_code), None, detail)


def verb(roster: Path, grantor: str, scope: list[str], ttl_days: int,
         manifest: Path | None) -> tuple[int, str]:
    argv = ["doa", "check", "--roster", str(roster), "--grantor", grantor,
            "--ttl-days", str(ttl_days), "--agent-id", AGENT_ID]
    for s in scope:
        argv += ["--scope", s]
    if manifest is not None:
        argv += ["--manifest", str(manifest)]
    result = CliRunner().invoke(cli_app, argv)
    return result.exit_code, result.output.strip()


def verb_outcome(code: int, output: str) -> tuple[str, str | None, str]:
    if code == 0:
        assert output.startswith("ALLOW "), output
        return ("ALLOW", None, "")
    assert code == 1, (code, output)
    m = LINE.match(output)
    assert m, output
    return (m["status"], m["clause"], m["message"])


# --- the same inputs through the route and the verb ----------------------------

# (case id, roster overrides, grantor, scope, ttl_days, manifest kind, expected status, clause, message part)
CASES = [
    ("allow", {}, GRANTOR, ["read timesheets", "draft invoices"], 30, "valid",
     "ALLOW", None, ""),
    ("grantor-off-roster", {}, "Someone Else, Nowhere Inc", ["read timesheets"], 1, "valid",
     "403", "D.grantor", "is not on the DOA roster"),
    ("grantor-near-miss", {}, GRANTOR.lower(), ["read timesheets"], 1, "valid",
     "403", "D.grantor", "is not on the DOA roster"),
    ("grantor-inactive", {"active": False}, GRANTOR, ["read timesheets"], 1, "valid",
     "403", "D.grantor", "inactive"),
    ("scope-beyond-grantor", {"allowed_scope": ["read timesheets"]}, GRANTOR,
     ["read timesheets", "draft invoices"], 1, "valid", "403", "D.grantor", "may not delegate"),
    ("scope-beyond-manifest", {"allowed_scope": [*MANIFEST_SCOPE, "wire funds"]}, GRANTOR,
     ["wire funds"], 1, "valid", "422", "D.scope", "outside the agent manifest"),
    ("ttl-beyond-max", {"max_ttl_days": 1}, GRANTOR, ["read timesheets"], 2, "valid",
     "403", "D.grantor", "max_ttl_days=1"),
    ("manifest-no-ref", {}, GRANTOR, ["read timesheets"], 1, "none",
     "422", "D.scope", "(no_ref)"),
    ("manifest-missing", {}, GRANTOR, ["read timesheets"], 1, "missing",
     "422", "D.scope", "(missing)"),
    ("manifest-invalid", {}, GRANTOR, ["read timesheets"], 1, "invalid",
     "422", "D.scope", "(invalid)"),
    ("roster-missing", None, GRANTOR, ["read timesheets"], 1, "valid",
     "503", None, "DOA roster unavailable"),
    ("roster-unknown-key", {"max_spend_cad": 500}, GRANTOR, ["read timesheets"], 1, "valid",
     "503", None, "not a valid DOA roster"),
]


@pytest.mark.parametrize(
    "roster_over,grantor,scope,ttl_days,manifest_kind,status,clause,part",
    [c[1:] for c in CASES], ids=[c[0] for c in CASES],
)
def test_the_verb_and_the_route_agree(tmp_path, monkeypatch, roster_over, grantor, scope,
                                      ttl_days, manifest_kind, status, clause, part):
    files = tmp_path / "files"
    files.mkdir()
    roster = files / "not-there.yaml" if roster_over is None else write_roster(files, **roster_over)
    manifest = {
        "valid": lambda: write_manifest(files),
        "invalid": lambda: write_manifest(files, valid=False),
        "missing": lambda: files / "gone.yaml",
        "none": lambda: None,
    }[manifest_kind]()

    monkeypatch.setenv("FIELD_DOA_ROSTER", str(roster))
    route = Route(tmp_path, manifest).mint(grantor, scope, ttl_days)

    monkeypatch.delenv("FIELD_DOA_ROSTER")
    code, output = verb(roster, grantor, scope, ttl_days, manifest)
    said = verb_outcome(code, output)

    assert route == said
    assert said[0] == status and said[1] == clause
    assert part in said[2]


def test_allow_at_exactly_max_ttl_days_and_refuse_one_second_later_in_both(tmp_path, monkeypatch):
    """The boundary is `lifetime > max_ttl_days`: 30 days on a 30-day row is
    allowed by both; the verb takes whole days, so 31 is its first refusal."""
    roster = write_roster(tmp_path, max_ttl_days=30)
    manifest = write_manifest(tmp_path)
    assert verb(roster, GRANTOR, ["read timesheets"], 30, manifest)[0] == 0
    assert verb(roster, GRANTOR, ["read timesheets"], 31, manifest)[0] == 1

    monkeypatch.setenv("FIELD_DOA_ROSTER", str(roster))
    route = Route(tmp_path, manifest)
    ok = route.delegation.post("/tokens", json={
        "agent_id": AGENT_ID, "granted_by": GRANTOR, "scope": ["read timesheets"],
        "ttl_seconds": 30 * 86400})
    over = route.delegation.post("/tokens", json={
        "agent_id": AGENT_ID, "granted_by": GRANTOR, "scope": ["read timesheets"],
        "ttl_seconds": 30 * 86400 + 1})
    assert (ok.status_code, over.status_code) == (201, 403)


# --- the verb is a dry run -----------------------------------------------------


def test_the_verb_mints_nothing_writes_nothing_and_connects_nowhere(tmp_path, monkeypatch):
    """ALLOW path, with every way to persist or connect booby-trapped: the real
    TokenStore, the real ledger and registry clients, and httpx. The working
    directory and FIELD_DATA_DIR stay empty."""
    import httpx

    import delegation_authority.api as api_module
    import delegation_authority.store as store_module

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    roster = write_roster(inputs)
    manifest = write_manifest(inputs)
    before = sorted(p.name for p in inputs.iterdir())

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))

    def explode(*a, **k):
        raise AssertionError("doa check must not construct a store, a client or a connection")

    monkeypatch.setattr(store_module, "TokenStore", explode)
    monkeypatch.setattr(api_module, "TokenStore", explode)
    monkeypatch.setattr(api_module, "LedgerClient", explode)
    monkeypatch.setattr(api_module, "RegistryClient", explode)
    for name in ("Client", "AsyncClient", "post", "get", "request"):
        monkeypatch.setattr(httpx, name, explode)

    code, output = verb(roster, GRANTOR, ["read timesheets"], 30, manifest)
    assert code == 0, output
    assert output.startswith("ALLOW ")
    assert list(work.iterdir()) == []
    assert not (tmp_path / "data").exists()
    assert sorted(p.name for p in inputs.iterdir()) == before


def test_the_verb_uses_the_routes_own_gate_not_a_copy(tmp_path, monkeypatch):
    """If the gate were re-implemented in the CLI, patching the route module's
    resolver would change nothing the verb says."""
    import delegation_authority.api as api_module

    monkeypatch.setattr(api_module, "resolve_manifest_detail", lambda ref: (None, "patched-in-route"))
    code, output = verb(write_roster(tmp_path), GRANTOR, ["read timesheets"], 1, write_manifest(tmp_path))
    assert code == 1
    assert "(patched-in-route)" in output


def test_the_verb_never_says_allow_when_the_roster_gate_did_not_run(tmp_path, monkeypatch):
    """Reaching the ledger write is only an ALLOW if the route recorded
    `doa_checked: true`. A route that skipped the gate (here: the arming check
    patched off) must produce no verdict, never a green line."""
    import delegation_authority.api as api_module

    monkeypatch.setattr(api_module, "roster_path", lambda: None)
    code, output = verb(write_roster(tmp_path), "Someone Else, Nowhere Inc",
                        ["read timesheets"], 1, write_manifest(tmp_path))
    assert code == 2
    assert "ALLOW" not in output
    assert "without running the DOA roster gate" in output


@pytest.mark.parametrize("preset", [None, "/data/doa-roster.yaml"])
def test_the_verb_restores_field_doa_roster_exactly(tmp_path, monkeypatch, preset):
    import os

    if preset is None:
        monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)
    else:
        monkeypatch.setenv("FIELD_DOA_ROSTER", preset)
    for grantor in (GRANTOR, "Someone Else"):  # the ALLOW and the REFUSED exits
        verb(write_roster(tmp_path), grantor, ["read timesheets"], 1, write_manifest(tmp_path))
        assert os.environ.get("FIELD_DOA_ROSTER") == preset


def test_a_fault_inside_the_gate_is_no_verdict_never_a_refusal(tmp_path, monkeypatch):
    """An exception is not a clause. Uncaught, the CLI would exit 1 — the
    REFUSED code — and a pre-arm dry run would read a crash as a verdict."""
    import delegation_authority.api as api_module

    def boom(ref):
        raise RuntimeError("resolver fault")

    monkeypatch.setattr(api_module, "resolve_manifest_detail", boom)
    code, output = verb(write_roster(tmp_path), GRANTOR, ["read timesheets"], 1, write_manifest(tmp_path))
    assert code == 2
    assert "resolver fault" in output
    assert "REFUSED" not in output and "ALLOW" not in output


def test_a_handler_that_never_reaches_the_ledger_is_no_verdict(tmp_path, monkeypatch):
    """If the handler returned normally, the dry-run ledger never saw an append:
    the verb cannot know the gate passed, so it must not say ALLOW."""
    import delegation_authority.cli as cli_module

    monkeypatch.setattr(cli_module._DryRunLedger, "append", lambda self, *a, **k: None)
    monkeypatch.setattr(cli_module._DryRunStore, "save", lambda self, token: token)
    code, output = verb(write_roster(tmp_path), GRANTOR, ["read timesheets"], 1, write_manifest(tmp_path))
    assert code == 2
    assert "without reaching its ledger write" in output
    assert "ALLOW" not in output


def test_an_invalid_request_is_no_verdict(tmp_path):
    code, output = verb(write_roster(tmp_path), GRANTOR, ["read timesheets"], 0, write_manifest(tmp_path))
    assert code == 2
    assert "ALLOW" not in output and "REFUSED" not in output


def test_the_shipped_example_roster_allows_both_ssl_agents_their_full_scope():
    """Operator smoke on the repo's own files: every scope each ssl manifest
    declares clears the example roster for 30 days."""
    repo = Path(__file__).resolve().parents[3]
    roster = repo / "manifests" / "doa-roster.example.yaml"
    for name in ("ssl-invoicing-agent", "ssl-timekeeping-agent"):
        manifest = repo / "manifests" / f"{name}.yaml"
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        argv = ["doa", "check", "--roster", str(roster), "--grantor", data["delegation"]["granted_by"],
                "--ttl-days", "30", "--manifest", str(manifest)]
        for s in data["delegation"]["scope"]:
            argv += ["--scope", s]
        result = CliRunner().invoke(cli_app, argv)
        assert result.exit_code == 0, result.output
        assert f"agent='{name}'" in result.output


# --- the registry's manifest_ref, verbatim ---------------------------------------


def _write_scoped_manifest(directory: Path, scope: list[str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = write_manifest(directory)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["delegation"]["scope"] = list(scope)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("case", ["cwd-has-no-copy", "cwd-has-a-broader-copy"])
def test_a_relative_manifest_ref_resolves_like_the_route(tmp_path, monkeypatch, case):
    """The route resolves the registry's RELATIVE manifest_ref against
    FIELD_MANIFEST_DIR. The verb must hand the same string to the same resolver,
    not absolutise it against its own working directory first: otherwise a
    pasted ref gives a false REFUSED (no copy in the CWD) or a false ALLOW (a
    broader same-named manifest in the CWD)."""
    estate = tmp_path / "estate-manifests"
    _write_scoped_manifest(estate, MANIFEST_SCOPE)
    work = tmp_path / "work"
    work.mkdir()
    if case == "cwd-has-a-broader-copy":
        _write_scoped_manifest(work, [*MANIFEST_SCOPE, "wire funds"])
        scope = ["wire funds"]
        expected = ("422", "D.scope", "outside the agent manifest")
    else:
        scope = ["read timesheets"]
        expected = ("ALLOW", None, "")
    ref = "agent-manifest.yaml"  # exactly as the registry record holds it
    roster = write_roster(tmp_path, allowed_scope=[*MANIFEST_SCOPE, "wire funds"])
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(estate))
    monkeypatch.chdir(work)

    monkeypatch.setenv("FIELD_DOA_ROSTER", str(roster))
    route = Route(tmp_path, ref).mint(GRANTOR, scope, 1)
    monkeypatch.delenv("FIELD_DOA_ROSTER")

    argv = ["doa", "check", "--roster", str(roster), "--grantor", GRANTOR, "--ttl-days", "1",
            "--agent-id", AGENT_ID, "--manifest-ref", ref]
    for s in scope:
        argv += ["--scope", s]
    result = CliRunner().invoke(cli_app, argv)
    said = verb_outcome(result.exit_code, result.output.strip())

    assert route == said
    assert (said[0], said[1]) == expected[:2] and expected[2] in said[2]
