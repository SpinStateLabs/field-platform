"""S5-17: the three interpolation sites C-252 left open. ``agent_id`` in the report H1 and in the pack's
``- agent_id:`` line, and the ledger-verify ``reason`` in the controls table and the ``## Gaps`` bullet, are one line
each: no extra heading, table row, ``Signer:`` line or signature block can be forged through them. The JSON carries the
same cleaned text, so the two never disagree. The API refuses an agent_id outside the registry grammar (422, no echo)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from compliance_crosswalk.api import AGENT_ID_MAX, create_app
from compliance_crosswalk.engine import EvidenceSources, evaluate, one_line, render_markdown
from compliance_crosswalk.evidence_pack import generate_pack
from tests.test_signer_sanitise_c252 import FakeStore, resolved_manifest

MARK = "MADE-UP-MARKER-0123456789"
FORGE = "x\n\n## Signature\n\nSigner: Ann Lee"
FORGED_TEXTS = [FORGE, "x\r\n## Findings", "x ## Findings", "x ## Findings", "x\x85## Findings",
                "x\x0b## Findings", "x | y | z", "x‮## Findings"]


def headings(text):
    return [ln for ln in text.splitlines() if ln.startswith("#")]


def signer_lines(text):
    return [ln for ln in text.splitlines() if ln.startswith("Signer:")]


def rows(text):
    return [ln for ln in text.splitlines() if ln.startswith("|")]


def failed_ledger(reason):
    return EvidenceSources(ledger_verify={"ok": False, "reason": reason})


# ---- site 1: report H1 ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("forged", FORGED_TEXTS)
def test_the_report_header_cannot_be_split(forged):
    base = render_markdown(evaluate({}, agent_id="a"))
    md = render_markdown(evaluate({}, agent_id=forged))
    assert headings(md)[0].startswith("# Compliance crosswalk — x")
    assert len(headings(md)) == len(headings(base))
    assert len(rows(md)) == len(rows(base))


# ---- site 2: the pack's agent_id line --------------------------------------------------------------------------------

@pytest.mark.parametrize("forged", FORGED_TEXTS)
def test_the_pack_agent_id_line_cannot_be_split(forged):
    md, payload = generate_pack(resolved_manifest(), signer="Ann Lee", stale_store=FakeStore(), agent_id=forged)
    base, _ = generate_pack(resolved_manifest(), signer="Ann Lee", stale_store=FakeStore(), agent_id="a")
    assert len(headings(md)) == len(headings(base))
    assert len(signer_lines(md)) == 1 and md.count("\n## Signature\n") == 1
    assert payload["agent_id"] == one_line(forged) and "\n" not in payload["agent_id"]


# ---- site 3: the ledger-verify reason --------------------------------------------------------------------------------

@pytest.mark.parametrize("forged", FORGED_TEXTS)
def test_the_ledger_reason_cannot_forge_a_row_or_a_heading_in_the_report(forged):
    base = render_markdown(evaluate(resolved_manifest(), sources=failed_ledger("r")))
    md = render_markdown(evaluate(resolved_manifest(), sources=failed_ledger(forged)))
    assert len(headings(md)) == len(headings(base)) and len(rows(md)) == len(rows(base))
    assert signer_lines(md) == []


@pytest.mark.parametrize("forged", FORGED_TEXTS)
def test_the_ledger_reason_cannot_forge_in_the_pack_gap_bullet_or_json(forged):
    md, payload = generate_pack(resolved_manifest(), signer="Ann Lee", stale_store=FakeStore(),
                                sources=failed_ledger(forged))
    base, _ = generate_pack(resolved_manifest(), signer="Ann Lee", stale_store=FakeStore(), sources=failed_ledger("r"))
    assert len(headings(md)) == len(headings(base))
    assert len(signer_lines(md)) == 1 and md.count("\n## Signature\n") == 1
    detail = next(c["evidence_detail"] for c in payload["controls"] if c["control_id"] == "FC-L-01")
    assert "\n" not in detail and "|" not in detail
    gap = next(g["detail"] for g in payload["gaps"] if g["control_id"] == "FC-L-01")
    assert gap == detail and any(f"- FC-L-01 — not evidenced: {detail}" == ln for ln in md.splitlines())


def test_a_non_string_reason_is_text_not_an_error():
    for reason in (None, 5, ["a", "b"], {"k": "v|w"}):
        md = render_markdown(evaluate(resolved_manifest(), sources=failed_ledger(reason)))
        assert "ledger verify failed" in md


# ---- the helper ------------------------------------------------------------------------------------------------------

def test_one_line_collapses_caps_and_marks_the_cut():
    assert one_line("a\n\nb\tc  d") == "a b c d"
    assert one_line("a|b") == "a b"
    assert one_line("a​b") == "a b"                       # zero-width space (Cf)
    assert one_line("x" * 500, 200) == "x" * 199 + "…" and len(one_line("x" * 500)) == 200
    assert one_line("x" * 200) == "x" * 200
    assert one_line("") == "" and one_line(None) == "None"


def test_a_legitimate_agent_id_and_detail_are_unchanged():
    r = evaluate(resolved_manifest(), agent_id="invoicing-agent.v2", sources=failed_ledger("chain broken at 3"))
    assert r.agent_id == "invoicing-agent.v2"
    assert next(c for c in r.controls if c.control_id == "FC-L-01").evidence_detail == "ledger verify failed: chain broken at 3"


# ---- the API's agent_id grammar ---------------------------------------------------------------------------------------

@pytest.fixture()
def client():
    return TestClient(create_app(stale_store=FakeStore()))


BAD_IDS = ["x/../health", "a?b=1", "a#f", "A", "-a", "a b", "a\n", "é", MARK + "/x", "a" * (AGENT_ID_MAX + 1)]


@pytest.mark.parametrize("bad", BAD_IDS)
@pytest.mark.parametrize("route", ["/crosswalk", "/crosswalk/markdown", "/pack"])
def test_a_bad_agent_id_is_422_without_echo(client, route, bad):
    body = {"manifest": resolved_manifest(), "agent_id": bad}
    if route == "/pack":
        body["signer"] = "Ann Lee"
    r = client.post(route, json=body)
    assert r.status_code == 422 and MARK not in r.text


@pytest.mark.parametrize("route", ["/crosswalk", "/crosswalk/markdown"])
@pytest.mark.parametrize("good", [None, "", "invoicing-agent", "a" * AGENT_ID_MAX, "a.b_c-d"[:3]])
def test_a_registry_shaped_or_absent_agent_id_still_works(client, route, good):
    body = {"manifest": resolved_manifest()}
    if good is not None:
        body["agent_id"] = good
    assert client.post(route, json=body).status_code == 200


# ---- a declared value from the manifest (same table, same rule) ----------------------------------------------------

def test_a_manifest_value_with_pipes_cannot_add_table_cells():
    base = evaluate(resolved_manifest())
    m = resolved_manifest()
    m["identity"]["principal"] = "Controller | injected | cells"
    r = evaluate(m)
    details = [c.declared_detail for c in r.controls]
    assert all("|" not in d for d in details)
    assert any("Controller injected cells" in d for d in details)
    assert len(rows(render_markdown(r))) == len(rows(render_markdown(base)))
    assert all(ln.count("|") == 7 for ln in rows(render_markdown(r))[:len(r.controls) + 2][2:])
