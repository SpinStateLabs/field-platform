"""G21 (architect decision 2026-11-05, rows C1/T6): the Stage 3 identity gap is closed WITHOUT giving a job row
`registry_edit` or `bypass_operator_list`.

* An unchanged re-provision (a token renewal) sends no PATCH (P29), so `job-provision-gb10` renews an alias-listed
  agent under FIELD_OPERATOR_REQUIRE.
* A change of owner or manifest_ref is a HUMAN edit by `don-admin` (the only row with `registry_edit`). The manifest
  lists `don-admin`, so the list check passes for it. A job identity that attempts the change gets 403, and the
  engine reports `edit_refused`, once, never retried; the CLI exits 1.
* OFF and LOG-ONLY output is unchanged (golden).

Real registry, ledger, delegation, governor and kill-switch apps over TestClient; the operator flags are set only
inside the tests that need them. All keys are throwaway constants."""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core import operator_auth as oa
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from lifecycle_manager import cli
from lifecycle_manager.engine import LifecycleEngine
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

from test_transitions import VALID_MANIFEST

REPO = pathlib.Path(__file__).resolve().parents[3]
AGENT = "invoicing-agent"
ALIAS = "Don Hagell, Spin State Labs"
KEY_JOB = "tkv-g21-job-key-0123456789abcdef"
KEY_ADMIN = "tkv-g21-admin-key-0123456789abcdef"
KEY_DON = "tkv-g21-don-key-0123456789abcdef"
LIST = "      - Controller, Spin State Labs (test)\n"


def _manifest(*operators: str) -> str:
    assert LIST in VALID_MANIFEST
    return VALID_MANIFEST.replace(LIST, "".join(f"      - {o}\n" for o in operators))


def rows() -> list[dict]:
    def row(op, key, scopes, **extra):
        return {"operator_id": op, "key_sha256": oa.key_sha256(key), "status": "active", "scopes": scopes, **extra}
    return [
        row("job-provision-gb10", KEY_JOB, ["register", "caps", "mint", "mint_for_others", "revoke"]),
        row("don-admin", KEY_ADMIN, ["registry_edit"]),
        row("don", KEY_DON, ["kill", "revive", "drill"], names=[ALIAS]),
    ]


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


class Spy:
    """The engine's registry HTTP client: forwards everything, records each PATCH."""

    def __init__(self, inner):
        self.inner = inner
        self.patches: list[tuple[str, dict]] = []

    def post(self, *a, **kw):
        return self.inner.post(*a, **kw)

    def get(self, *a, **kw):
        return self.inner.get(*a, **kw)

    def patch(self, url, json=None, **kw):  # noqa: A002
        self.patches.append((url, json))
        return self.inner.patch(url, json=json, **kw)


class Stack:
    def __init__(self, tmp: pathlib.Path, listed=(ALIAS, "don-admin")):
        self.tmp = tmp
        ledger_client = lambda: LedgerClient(client=self.ledger, base_url="http://t")  # noqa: E731
        self.ledger = TestClient(create_ledger_app(store=LedgerStore(tmp / "events.jsonl")))
        self.registry = TestClient(create_registry_app(store=RegistryStore(tmp / "agents.sqlite3"),
                                                       ledger=ledger_client()))
        registry_client = lambda: RegistryClient(client=self.registry, base_url="http://t")  # noqa: E731
        self.delegation = TestClient(create_delegation_app(
            store=TokenStore(tmp / "tokens.sqlite3"), ledger=ledger_client(), registry=registry_client()))
        self.governor = TestClient(create_governor_app(store=GovernorStore(tmp / "spend.sqlite3")))
        self.kill = TestClient(create_kill_app(registry=registry_client(), ledger=ledger_client()))
        self.spy = Spy(self.registry)
        self.engine_kwargs = dict(registry=registry_client(), delegation=self.delegation, ledger=ledger_client(),
                                  killswitch=self.kill, registry_http=self.spy, governor=self.governor)
        self.engine = LifecycleEngine(**self.engine_kwargs)
        self.manifest = tmp / "invoicing-agent.yaml"
        self.manifest.write_text(_manifest(*listed), encoding="utf-8")
        self.ref_a = self._ref("a", listed)
        self.ref_b = self._ref("b", listed)

    def _ref(self, name: str, listed) -> str:
        path = self.tmp / name / "data" / "manifests" / "invoicing-agent.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(_manifest(*listed), encoding="utf-8")
        return str(path)

    def identify(self, operator_id: str, key: str) -> None:
        for client in (self.registry, self.delegation, self.governor):
            client.headers.update({oa.HEADER_OPERATOR: operator_id, oa.HEADER_KEY: key})

    def provision(self, owner="AP Team Lead", ref=None):
        return self.engine.provision(manifest_path=self.manifest, owner=owner, domain="finance",
                                     grantor="Controller", ttl_days=30, manifest_ref=ref or self.ref_a)

    def record(self) -> dict:
        return self.registry.get(f"/agents/{AGENT}").json()

    def events(self, event_type: str) -> list[dict]:
        return self.ledger.get("/events", params={"event_type": event_type}).json()


def _arm(stack, monkeypatch, tmp_path, *, require=True, mode_rows=None):
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps(mode_rows or rows()), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    if require:
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def _register(report):
    [step] = [s for s in report.steps if s.step == "register"]
    return step


# 1 ---------------------------------------------------------------------------------------------------------------

def test_an_alias_listed_agent_is_renewed_under_require_by_the_job_identity(tmp_path, monkeypatch):
    stack = Stack(tmp_path)
    first = stack.provision()                                       # first provision, flags off
    assert first.ok is True and first.registry_outcome == "registered"
    _arm(stack, monkeypatch, tmp_path)
    stack.identify("job-provision-gb10", KEY_JOB)
    stack.spy.patches.clear()

    again = stack.provision()

    assert again.ok is True, [(s.step, s.outcome, s.detail) for s in again.steps]
    assert again.registry_outcome == "unchanged" and stack.spy.patches == []
    assert again.token_id and again.token_id != first.token_id      # a new token was minted


# 2 ---------------------------------------------------------------------------------------------------------------

def test_the_job_identity_cannot_change_the_manifest_ref_and_the_engine_reports_edit_refused(tmp_path, monkeypatch):
    stack = Stack(tmp_path)
    assert stack.provision().ok is True
    before = stack.record()
    _arm(stack, monkeypatch, tmp_path)
    stack.identify("job-provision-gb10", KEY_JOB)
    stack.spy.patches.clear()

    changed = stack.provision(ref=stack.ref_b)

    assert len(stack.spy.patches) == 1                              # sent once, never retried
    step = _register(changed)
    assert step.outcome == "failed" and step.http_status == 403
    assert "don-admin" in step.detail and "not retried" in step.detail
    assert changed.ok is False and changed.registry_outcome == "edit_refused"
    assert changed.token_id is None                                 # the run stopped at register
    assert stack.record() == before                                 # nothing was written


def test_the_command_line_exits_one_and_names_the_actor_when_the_edit_is_refused(tmp_path, monkeypatch):
    stack = Stack(tmp_path)
    assert stack.provision().ok is True
    _arm(stack, monkeypatch, tmp_path)
    stack.identify("job-provision-gb10", KEY_JOB)
    monkeypatch.setattr(cli, "_provision_clients", lambda pair=None: stack.engine_kwargs)
    key_file = tmp_path / "job.key"
    key_file.write_text(KEY_JOB, encoding="utf-8")
    result = CliRunner().invoke(cli.app, [
        "provision", "--manifest", str(stack.manifest), "--owner", "AP Team Lead", "--domain", "finance",
        "--ttl-days", "30", "--manifest-ref", stack.ref_b, "--grantor", "Controller",
        "--operator-id", "job-provision-gb10", "--operator-key-file", str(key_file)])
    assert result.exit_code == 1
    assert '"registry_outcome": "edit_refused"' in result.output and "don-admin" in result.output


# 3 ---------------------------------------------------------------------------------------------------------------

class RecordingLedger:
    """The registry's own ledger append: the authenticated id is merged into the payload inside it."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def append(self, event_type, payload, agent_id=None):
        self.events.append((event_type, payload))


def test_don_admin_changes_the_manifest_ref_and_the_ledger_carries_its_id(tmp_path, monkeypatch):
    stack = Stack(tmp_path)
    ledger = RecordingLedger()
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "own.sqlite3"), ledger=ledger))
    assert registry.post("/agents", json={"agent_id": AGENT, "name": AGENT, "owner": "AP Team Lead",
                                          "domain": "finance", "manifest_ref": stack.ref_a}).status_code == 201
    _arm(stack, monkeypatch, tmp_path)
    r = registry.patch(f"/agents/{AGENT}", json={"manifest_ref": stack.ref_b},
                       headers={oa.HEADER_OPERATOR: "don-admin", oa.HEADER_KEY: KEY_ADMIN})
    assert r.status_code == 200 and r.json()["manifest_ref"] == stack.ref_b
    [payload] = [p for t, p in ledger.events if t == "registry.updated"]
    assert payload["operator_id_authenticated"] == "don-admin"


def test_a_manifest_that_lists_only_the_alias_still_refuses_don_admin(tmp_path, monkeypatch):
    stack = Stack(tmp_path, listed=(ALIAS,))                        # the alias only: no don-admin
    assert stack.provision().ok is True
    _arm(stack, monkeypatch, tmp_path)
    r = stack.registry.patch(f"/agents/{AGENT}", json={"manifest_ref": stack.ref_b},
                             headers={oa.HEADER_OPERATOR: "don-admin", oa.HEADER_KEY: KEY_ADMIN})
    assert r.status_code == 403
    assert stack.record()["manifest_ref"] == stack.ref_a


# 4 ---------------------------------------------------------------------------------------------------------------

def test_no_row_gains_registry_edit_or_the_list_exemption_and_don_admin_cannot_kill():
    by_id = {r["operator_id"]: r for r in rows()}
    job = by_id["job-provision-gb10"]["scopes"]
    assert "registry_edit" not in job and "bypass_operator_list" not in job and "names" not in by_id["job-provision-gb10"]
    assert "mint_for_others" in job                                 # C1 mints with a display-name grantor
    assert by_id["don-admin"]["scopes"] == ["registry_edit"]
    assert not {"kill", "revive", "*"} & set(by_id["don-admin"]["scopes"])
    assert by_id["don"]["names"] == [ALIAS] and "registry_edit" not in by_id["don"]["scopes"]


def test_no_operators_row_is_shipped_in_this_repository_with_the_list_exemption():
    """No operators file is committed here (the ten-row file is assembled outside the repository), so this scans
    every committed data file outside the tests for a row that holds both a key hash and the exemption, and
    holds the line if one is ever added: only a service row may."""
    offenders = []
    for path in REPO.rglob("*"):
        if (path.suffix not in (".json", ".yaml", ".yml") or ".git" in path.parts or "tests" in path.parts
                or "node_modules" in path.parts or ".pytest_cache" in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "bypass_operator_list" in text and "key_sha256" in text:
            for m in re.finditer(r'"operator_id"\s*:\s*"([^"]+)"[^{}]*"bypass_operator_list"', text):
                if not m.group(1).startswith("svc-") or m.group(1).startswith("svc-verifier-"):
                    offenders.append((str(path.relative_to(REPO)), m.group(1)))
    assert offenders == []


def test_the_estate_self_agent_manifests_list_the_alias_and_don_admin():
    """The three estate self-agents whose tokens `lifecycle provision` renews (not the canaries, whose lists are
    pinned by the verifier tests; not the demo and template manifests, which no operator row names)."""
    import yaml
    for name in ("deployment-agent", "ssl-timekeeping-agent", "ssl-invoicing-agent"):
        listed = yaml.safe_load((REPO / "manifests" / f"{name}.yaml").read_text(encoding="utf-8"))[
            "enforcement"]["kill_switch"]["authorized_operators"]
        assert listed == [ALIAS, "don-admin"], name


# 5 ---------------------------------------------------------------------------------------------------------------

def _normalise(report) -> str:
    text = report.model_dump_json(indent=2)
    text = re.sub(r'"(token_id|expires_at|provisioned_at)": "[^"]*"', r'"\1": "<var>"', text)
    return text.replace(str(pathlib.Path(report.manifest).parent), "<dir>")


@pytest.mark.parametrize("mode", ["off", "log-only"])
def test_off_and_log_only_provision_output_is_unchanged(mode, tmp_path, monkeypatch):
    """Golden: the three reports of a register, an unchanged re-run and a changed owner, in OFF and in LOG-ONLY. The
    file was produced from main BEFORE this change (see the card); a diff here means flags-off output moved."""
    stack = Stack(tmp_path)
    if mode == "log-only":
        _arm(stack, monkeypatch, tmp_path, require=False)
        stack.identify("job-provision-gb10", KEY_JOB)
    out = [_normalise(stack.provision()), _normalise(stack.provision()), _normalise(stack.provision(owner="Someone Else"))]
    golden = json.loads((pathlib.Path(__file__).parent / "golden" / "provision_g21.json").read_text(encoding="utf-8"))
    assert out == golden[mode]
