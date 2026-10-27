"""P29 (DECISIONS-FOR-DON; runbook OPEN ITEM rows C1/T6): a re-provision whose owner and
manifest_ref already equal the registry's stored values sends NO registry PATCH, so it
does not need registry_edit (plus the manifest's authorized_operators) under
FIELD_OPERATOR_REQUIRE. A real change still PATCHes, and is still gated.

Why: `lifecycle provision` is how the Fly/GB10 self-agent tokens are renewed. It always
PATCHed {owner, manifest_ref} on the 409, an edit that only don-admin may make under
REQUIRE (design v0.4 2.2.1), so every renewal by `job-provision-gb10` or `don` would stop
at the register step with a 403 at Stage 3.

Real registry, ledger, delegation, governor and kill-switch apps over TestClient; the
registry's HTTP client is wrapped so every PATCH the engine sends is recorded. The
operator flags are set only inside the test that needs them (monkeypatch)."""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core import operator_auth as oa
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from lifecycle_manager.engine import LifecycleEngine
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

from test_transitions import VALID_MANIFEST

AGENT = "invoicing-agent"
KEY_JOB = "tkv-p29-job-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


class Spy:
    """The engine's registry HTTP client: forwards everything, records each PATCH."""

    def __init__(self, inner, get_status: int | None = None):
        self.inner, self.get_status = inner, get_status
        self.patches: list[tuple[str, dict]] = []

    def post(self, *a, **kw):
        return self.inner.post(*a, **kw)

    def get(self, *a, **kw):
        if self.get_status is not None:
            class Broken:
                status_code, text = self.get_status, "simulated"

                def json(self):
                    raise ValueError("no body")
            return Broken()
        return self.inner.get(*a, **kw)

    def patch(self, url, json=None, **kw):  # noqa: A002
        self.patches.append((url, json))
        return self.inner.patch(url, json=json, **kw)


class Stack:
    def __init__(self, tmp_path: pathlib.Path):
        self.ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
        self.registry = TestClient(create_registry_app(
            store=RegistryStore(tmp_path / "agents.sqlite3"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t")))
        delegation = TestClient(create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t"),
            registry=RegistryClient(client=self.registry, base_url="http://t")))
        governor = TestClient(create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3")))
        kill = TestClient(create_kill_app(
            registry=RegistryClient(client=self.registry, base_url="http://t"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t")))
        self.spy = Spy(self.registry)
        self.engine = LifecycleEngine(
            registry=RegistryClient(client=self.registry, base_url="http://t"),
            delegation=delegation, ledger=LedgerClient(client=self.ledger, base_url="http://t"),
            killswitch=kill, registry_http=self.spy, governor=governor)
        self.manifest = tmp_path / "invoicing-agent.yaml"
        self.manifest.write_text(VALID_MANIFEST, encoding="utf-8")
        self.ref_a = self._ref(tmp_path / "a")
        self.ref_b = self._ref(tmp_path / "b")

    @staticmethod
    def _ref(root: pathlib.Path) -> str:
        path = root / "data" / "manifests" / "invoicing-agent.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(VALID_MANIFEST, encoding="utf-8")
        return str(path)

    def provision(self, owner: str = "AP Team Lead", ref: str | None = None):
        return self.engine.provision(
            manifest_path=self.manifest, owner=owner, domain="finance", grantor="Controller",
            ttl_days=30, manifest_ref=ref or self.ref_a)

    def record(self) -> dict:
        return self.registry.get(f"/agents/{AGENT}").json()

    def events(self, event_type: str) -> list[dict]:
        return self.ledger.get("/events", params={"event_type": event_type}).json()


@pytest.fixture()
def stack(tmp_path):
    return Stack(tmp_path)


def _register(report):
    [step] = [s for s in report.steps if s.step == "register"]
    return step


def test_an_unchanged_re_provision_sends_no_patch_and_reports_unchanged(stack):
    first = stack.provision()
    assert first.ok is True and first.registry_outcome == "registered"
    record_before = stack.record()
    stack.spy.patches.clear()

    again = stack.provision()

    assert stack.spy.patches == []                                  # nothing sent to the registry
    assert again.registry_outcome == "unchanged"
    step = _register(again)
    assert step.outcome == "ok" and "unchanged" in step.detail and "no PATCH" in step.detail
    assert again.ok is True and again.token_id and again.token_id != first.token_id  # renewal minted
    assert stack.record() == record_before                          # the row is untouched
    assert stack.events("registry.updated") == []                   # and nothing was ledgered as an edit


@pytest.mark.parametrize("change", ["owner", "manifest_ref", "both"])
def test_a_real_change_still_patches_and_reports_updated(stack, change):
    assert stack.provision().ok is True
    stack.spy.patches.clear()
    owner = "Someone Else" if change in ("owner", "both") else "AP Team Lead"
    ref = stack.ref_b if change in ("manifest_ref", "both") else stack.ref_a

    again = stack.provision(owner=owner, ref=ref)

    assert stack.spy.patches == [(f"/agents/{AGENT}", {"owner": owner, "manifest_ref": ref})]
    assert again.ok is True and again.registry_outcome == "updated"
    assert "updated" in _register(again).detail
    assert (stack.record()["owner"], stack.record()["manifest_ref"]) == (owner, ref)
    assert len(stack.events("registry.updated")) == 1


def test_an_unreadable_record_falls_through_to_the_patch_as_before(stack):
    assert stack.provision().ok is True
    stack.spy.patches.clear()
    stack.spy.get_status = 500                                      # the GET after the 409 fails

    again = stack.provision()

    assert len(stack.spy.patches) == 1 and again.registry_outcome == "updated"


def test_under_require_a_job_identity_renews_unchanged_but_a_change_is_still_refused(stack, tmp_path,
                                                                                   monkeypatch):
    """The P29 failure itself: a job identity without registry_edit. Unchanged: no PATCH, the
    register step passes. Changed owner: the PATCH is sent and the registry refuses it (403),
    so the gate on a real edit is unchanged."""
    assert stack.provision().ok is True                             # first provision, flags off
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps([{"operator_id": "job-provision-gb10", "key_sha256": oa.key_sha256(KEY_JOB),
                                "status": "active", "scopes": ["register", "caps", "mint", "revoke"]}]),
                   encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    stack.registry.headers.update({oa.HEADER_OPERATOR: "job-provision-gb10", oa.HEADER_KEY: KEY_JOB})
    stack.spy.patches.clear()

    unchanged = stack.provision()
    assert stack.spy.patches == [] and unchanged.registry_outcome == "unchanged"
    assert _register(unchanged).outcome == "ok"

    changed = stack.provision(owner="Someone Else")
    assert len(stack.spy.patches) == 1
    step = _register(changed)
    assert step.outcome == "failed" and step.http_status == 403 and "PATCH refused" in step.detail
    assert changed.ok is False and changed.registry_outcome is None
    assert stack.record()["owner"] == "AP Team Lead"                # the refused edit wrote nothing
