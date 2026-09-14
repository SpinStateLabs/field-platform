"""run_demo.sh's governed agent, in-process: the 5th draft ESCALATEs.

``integration/demo/run_demo.sh`` boots seven services on fixed ports, which CI
does not run. This test drives the SAME agent file
(``integration/demo/agent/invoicing_agent.py``), the SAME manifest and timesheet,
and the same operator steps run_demo.sh takes (register with the manifest, cap
and rate limits from the manifest through the loader ``governor set-cap
--from-manifest`` uses, the haiku-only 200k tokens/h policy, a 2-scope token)
against the real in-process spine from ``conftest.Stack`` in enforce mode. It
asserts what run_demo prints: INV-001..004 drafted, INV-005 ESCALATED
``E.spend_threshold`` (the meter at 96%), ``4 drafted, 1 escalated``, and the
rogue transfer BLOCKED. It also pins option B (the agent reports cents only;
the sentinel's metered ALLOWs are the action count) and the manifest's
``read timesheets`` rate limit. All data SYNTHETIC.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from field_core.manifest import FieldManifest
from field_core.validation import load_manifest
from spend_governor.core import SpendCapConfig
from spend_governor.provisioning import load_rate_limits, rate_limits_from_manifest

AGENT_ID = "invoicing-agent"
REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "integration" / "demo"
MANIFEST = DEMO / "manifests" / "invoicing-agent.yaml"
TIMESHEET = DEMO / "agent" / "timesheet.csv"


def _demo_agent_module():
    spec = importlib.util.spec_from_file_location(
        "demo_invoicing_agent", DEMO / "agent" / "invoicing_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operator_setup_like_run_demo(stack) -> str:
    """run_demo.sh steps 1-2, against the in-process stack."""
    r = stack.registry.patch(f"/agents/{AGENT_ID}", json={"manifest_ref": str(MANIFEST)})
    assert r.status_code == 200, r.text
    manifest = FieldManifest.from_dict(load_manifest(MANIFEST))
    cap = SpendCapConfig.from_manifest(manifest, AGENT_ID)
    r = stack.governor.put(f"/caps/{AGENT_ID}", json=cap.model_dump())
    assert r.status_code == 200, r.text
    loaded = load_rate_limits(
        lambda p: stack.governor.get(p),
        lambda p, json: stack.governor.put(p, json=json),
        rate_limits_from_manifest(manifest, AGENT_ID),
    )
    assert (loaded.outcome, loaded.detail) == ("loaded", "1 enforced, 0 declared-unenforced")
    stack.set_policy(allowed_models=["claude-haiku-4-5"], token_rate_limit=200_000)
    return stack.mint_token(scope=["read timesheets", "draft invoices"])


def test_run_demo_agent_escalates_the_fifth_draft(stack, tmp_path, monkeypatch, capsys):
    token = _operator_setup_like_run_demo(stack)
    demo = _demo_agent_module()
    # The agent builds FieldAgent(AGENT_ID, token_id=...) from env URLs; route
    # that one constructor to the in-process services instead of fixed ports.
    monkeypatch.setattr(
        demo, "FieldAgent",
        lambda agent_id, token_id=None: stack.make_agent(token_id=token_id, agent_id=agent_id))

    out_dir = tmp_path / "invoices"
    assert demo.main(timesheet=TIMESHEET, out_dir=out_dir, token_id=token) == 0
    out = capsys.readouterr().out

    for n, client in enumerate(["Acme Test Widgets Inc", "Borealis Example Corp",
                                "Cascadia Sample Ltd", "Dominion Placeholder Co"], start=1):
        assert f"INV-{n:03d} {client}: drafted" in out, out
    assert ("INV-005 Erewhon Fictional GmbH: ESCALATED to human queue "
            "[E.spend_threshold] — not drafted") in out, out
    assert "-- done: 4 drafted, 1 escalated --" in out, out
    assert "BLOCKED [D.scope] as designed" in out, out
    assert "!! ALLOWED" not in out
    assert sorted(p.name for p in out_dir.iterdir()) == [f"INV-{n:03d}.txt" for n in range(1, 5)]

    # Option B: every action is counted once, by the sentinel's metered ALLOWs
    # (1 read + 4 drafts; the ESCALATEd 5th draft and the BLOCKed transfer are
    # never metered); the agent's cents-only rows add no self-reported actions.
    status = stack.governor.get(f"/status/{AGENT_ID}").json()
    assert (status["spent_actions_metered"], status["spent_actions_self"],
            status["spent_actions"]) == (5, 0, 5)
    spend = [e for e in stack.events("spend.recorded") if e["agent_id"] == AGENT_ID]
    assert [(e["payload"]["actions"], e["payload"]["cents"], e["payload"].get("action"))
            for e in spend] == [(0, 12_000, "draft invoices")] * 4

    # The manifest's rate limit is live, and one run reads once (never exhausted).
    limits = stack.governor.get(f"/rate-limits/{AGENT_ID}").json()["rate_limits"]
    assert [(x["action"], x["max"], x["period"]) for x in limits] == [
        ("read timesheets", 10, "hourly")]
    reads = stack.governor.get(f"/status/{AGENT_ID}", params={"action": "read timesheets"}).json()
    assert reads["state"] != "THROTTLED" and reads["throttled"] is None, reads
