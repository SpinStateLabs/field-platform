"""F-CW-3 (reviewer C-1082, Lane 14): caller text reaches the pack Markdown on ONE line.

The signer is sanitised (C-252, C-389) but ``agent_id`` and a caller-supplied ``sources.ledger_verify.reason`` were
written into the pack Markdown raw: a newline in either started a new block, so a second ``## Signature`` heading with
``Signer: Mallory`` could appear in a pack handed to a named signer. Control, invisible-format and line-break
characters are now shown as ``<U+XXXX>`` on the one line; ordinary text is unchanged; the JSON keeps the value as given."""

from __future__ import annotations

import re

import pytest

from compliance_crosswalk.engine import EvidenceSources
from compliance_crosswalk.evidence_pack import generate_pack
from field_core.templates_api import template_data

INJECT = "x\n\n## Signature\n\nSigner: Mallory\n\nDate: 2026-01-01"


def _manifest():
    data = template_data("default")
    data["agent"]["name"] = "cw3-test-agent"
    data["agent"]["description"] = "exercises the one-line rendering"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/x"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = ["generate evidence packs"]
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://x"}
    return data


class _Store:
    def active(self):
        return []

    def status(self):
        return {"corpus_version": "corpus-test", "active": [], "history": []}


def _pack(agent_id=None, sources=None):
    return generate_pack(_manifest(), signer="Don Hagell", stale_store=_Store(), agent_id=agent_id, sources=sources)


def _headings(md: str, name: str) -> int:
    return len(re.findall(rf"(?m)^## {re.escape(name)}\b", md))


def test_a_newline_in_agent_id_cannot_start_a_second_signature_block():
    md, data = _pack(agent_id=INJECT)
    assert _headings(md, "Signature") == 1
    assert not re.search(r"(?m)^Signer: Mallory", md)
    (line,) = [ln for ln in md.splitlines() if ln.startswith("- agent_id:")]
    assert "<U+000A>" in line and "Mallory" in line          # visible, escaped, on the one line
    assert data["agent_id"] == INJECT                          # the JSON keeps the value as given


def test_a_newline_in_the_ledger_verify_reason_cannot_inject_a_heading_or_a_signer():
    reason = "tampered\n\n## Fake heading\n\nSigner: Mallory"
    md, _ = _pack(agent_id="agent-1", sources=EvidenceSources(ledger_verify={"ok": False, "reason": reason}))
    assert _headings(md, "Fake heading") == 0
    assert not re.search(r"(?m)^Signer: Mallory", md)
    gap = [ln for ln in md.splitlines() if "ledger verify failed" in ln]
    assert len(gap) == 1 and "<U+000A>" in gap[0] and "Fake heading" in gap[0]


@pytest.mark.parametrize("ch, code", [("\r", "000D"), ("\t", "0009"), ("\x00", "0000"), (" ", "2028"),
                                      (" ", "2029"), ("‮", "202E"), ("​", "200B"), ("\x7f", "007F")])
def test_every_refused_category_is_shown_as_its_code_point(ch, code):
    md, _ = _pack(agent_id=f"a{ch}b")
    (line,) = [ln for ln in md.splitlines() if ln.startswith("- agent_id:")]
    assert line == f"- agent_id: a<U+{code}>b"


@pytest.mark.parametrize("agent_id", ["agent-1", "Agent_7.v2", "ünïcode-agënt", "a b c"])
def test_ordinary_text_is_unchanged(agent_id):
    md, _ = _pack(agent_id=agent_id)
    assert f"- agent_id: {agent_id}" in md.splitlines()


def test_no_agent_id_still_reads_manifest_only():
    md, _ = _pack()
    assert "- agent_id: manifest-only" in md.splitlines()


def test_a_very_long_reason_is_capped_on_its_line():
    md, _ = _pack(agent_id="agent-1",
                  sources=EvidenceSources(ledger_verify={"ok": False, "reason": "r" * 5000}))
    (gap,) = [ln for ln in md.splitlines() if "ledger verify failed" in ln]
    assert len(gap) < 600 and gap.endswith("…")
