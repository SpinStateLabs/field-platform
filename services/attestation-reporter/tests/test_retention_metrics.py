"""C2 — the board pack's two scalar retention metrics (from GET /retention/check).

- "Estate ledger retention policy (days)": the estate's value, or unavailable.
- "Manifests declaring more retention than the estate keeps": a count; the
  offending ids and unresolvable refs are in ``note`` (``Metric.value`` is scalar).
Ledger missing / raising / 401, or no estate policy => both unavailable, no value.
The served pack equals the rendered one. The existing suites are unmodified.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import field_core
from attestation_reporter.api import create_app
from attestation_reporter.engine import BoardPack, PackEngine
from field_core.authn import ENV_VAR
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

POLICY = "Estate ledger retention policy (days)"
COUNT = "Manifests declaring more retention than the estate keeps"
TEMPLATES = Path(field_core.__file__).resolve().parent / "templates"


class StubRegistry:
    def __init__(self, agents):
        self.agents = agents

    def list_agents(self, *a, **k):
        return [dict(a) for a in self.agents]


class DeadRegistry:
    def list_agents(self, *a, **k):
        raise ConnectionError("registry down")


class _Unreachable:
    def get(self, *a, **k):
        raise httpx.ConnectError("connection refused")


def _manifest(tmp_path: Path, name: str, template: str) -> str:
    out = tmp_path / "manifests" / f"{name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text((TEMPLATES / f"field-manifest-{template}.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    return str(out)


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.delenv("FIELD_LEDGER_RETENTION_DAYS", raising=False)
    return monkeypatch


def _engine(tmp_path: Path, registry) -> PackEngine:
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl"), registry=registry))
    return PackEngine(ledger=ledger)


def _by_name(pack: BoardPack) -> dict:
    return {m.name: m for m in pack.all_metrics()}


def _registry(tmp_path: Path) -> StubRegistry:
    return StubRegistry([
        {"agent_id": "zz-invoicing", "manifest_ref": _manifest(tmp_path, "inv", "financial-agent")},  # 2555
        {"agent_id": "crm", "manifest_ref": _manifest(tmp_path, "crm", "client-facing-agent")},       # 730
        {"agent_id": "a9", "manifest_ref": str(tmp_path / "manifests" / "gone.yaml")},
        {"agent_id": "smoke-agent", "manifest_ref": None},
    ])


def test_attest_retention_metrics_present_and_ledger_down_unavailable(tmp_path, env):
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "365")
    stack = _engine(tmp_path, _registry(tmp_path))
    pack = stack.build(period="Q3 2026")
    section = next(s for s in pack.sections if s.title == "Ledger integrity")
    assert [m.name for m in section.metrics] == ["Ledger chain integrity", POLICY, COUNT]
    by_name = _by_name(pack)
    policy, count = by_name[POLICY], by_name[COUNT]
    for m in (policy, count):
        assert m.source_query == "GET http://127.0.0.1:8002/retention/check" and m.source_query.startswith("GET ")
    assert (policy.status, policy.value, policy.unit) == ("ok", 365, "days")
    assert (count.status, count.value, count.unit) == ("ok", 2, "manifests")
    assert count.note == ("offending: crm (730 d), zz-invoicing (2555 d); unresolvable: a9 (missing); "
                          "a lower bound: 1 manifest ref(s) could not be read; "
                          "1 agent(s) without a manifest_ref not checked")

    # served == rendered, metric for metric (generated_at differs; nothing else may)
    served = BoardPack.model_validate(TestClient(create_app(engine=stack)).get("/pack", params={"period": "Q3 2026"}).json())
    key = lambda m: (m.name, m.value, m.unit, m.status, m.source_query, m.note)  # noqa: E731
    assert [key(m) for m in served.all_metrics()] == [key(m) for m in stack.build(period="Q3 2026").all_metrics()]

    # ledger not configured / raising / 401: both unavailable, never a value
    down_note = "service not configured/reachable at generation time"
    for ledger in (None, _Unreachable()):
        stack.ledger = ledger
        by_name = _by_name(stack.build())
        for name in (POLICY, COUNT):
            assert by_name[name].status == "unavailable" and by_name[name].value is None, (ledger, name)
            assert by_name[name].source_query.startswith("GET ") and by_name[name].note == down_note
    stack = _engine(tmp_path / "authn", _registry(tmp_path))
    env.setenv(ENV_VAR, "s3cret-demo-only")  # the ledger now answers 401 to a caller without the header
    assert stack.ledger.get("/retention/check").status_code == 401
    by_name = _by_name(stack.build())
    assert by_name[POLICY].status == by_name[COUNT].status == "unavailable"
    assert by_name[POLICY].value is None and by_name[COUNT].value is None
    assert by_name[POLICY].note == by_name[COUNT].note == down_note  # a 401 is not "no estate policy"


def test_within_policy_counts_zero_and_no_policy_is_unavailable(tmp_path, env):
    registry = StubRegistry([{"agent_id": "inv", "manifest_ref": _manifest(tmp_path, "inv", "financial-agent")}])
    stack = _engine(tmp_path, registry)
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "2555")
    by_name = _by_name(stack.build())
    assert by_name[POLICY].value == 2555
    assert by_name[COUNT].value == 0 and by_name[COUNT].note == "none among 1 resolvable manifest(s)"
    env.delenv("FIELD_LEDGER_RETENTION_DAYS")
    by_name = _by_name(stack.build())
    for name in (POLICY, COUNT):
        assert by_name[name].status == "unavailable" and by_name[name].value is None
        assert by_name[name].note == "no estate policy (FIELD_LEDGER_RETENTION_DAYS unset)"


def test_registry_unreadable_by_the_ledger_keeps_the_policy_and_withholds_the_count(tmp_path, env):
    env.setenv("FIELD_LEDGER_RETENTION_DAYS", "2555")
    for registry in (DeadRegistry(), None):  # down, or the ledger app has none configured
        by_name = _by_name(_engine(tmp_path / type(registry).__name__, registry).build())
        assert by_name[POLICY].value == 2555
        assert by_name[COUNT].status == "unavailable" and by_name[COUNT].value is None
        assert "could not read the agent registry" in by_name[COUNT].note
