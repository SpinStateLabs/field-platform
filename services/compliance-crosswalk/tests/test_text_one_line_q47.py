"""Q-47 (reviewer Lane 7, PR 419): the one-line rule reaches every caller-text sink, and its edges are pinned.

F-Q47-1  ``render_markdown`` (POST /crosswalk/markdown) wrote ``agent_id`` (the H1) and the evidence detail (a table
         cell, carrying a caller-supplied ledger reason) raw: a newline injected a heading, a ``|`` added a column.
F-Q47-2  the staleness entries on the branch the code calls unreachable (framework, flagged_at, reason).
F-Q47-3  an unpaired surrogate: a 500 on POST /pack; now a named refusal (422), and shown escaped in Markdown.
F-Q47-4  the cap boundary (300 / 301), the cap applied to the ESCAPED line, an empty agent_id, no half token.
F-Q47-5  the gap labels "not declared" / "not evidenced" are on the right control ids."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from compliance_crosswalk.api import create_app
from compliance_crosswalk.engine import EvidenceSources, evaluate, render_markdown
from compliance_crosswalk.evidence_pack import generate_pack
from compliance_crosswalk.staleness import StaleStore
from compliance_crosswalk.textsafe import MAX_LINE_CHARS, one_line
from field_core.templates_api import template_data

TOKEN = re.compile(r"<U\+[0-9A-F]{4,6}>")


def _manifest():
    data = template_data("default")
    data["agent"]["name"] = "q47-test-agent"
    data["agent"]["description"] = "exercises the one-line rule"
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
    def __init__(self, active=(), status_active=()):
        self._active, self._status_active = list(active), list(status_active)

    def active(self):
        return list(self._active)

    def status(self):
        return {"corpus_version": "corpus-test", "active": list(self._status_active), "history": []}


# --- one_line itself -------------------------------------------------------------------------------------------------

def test_the_cap_boundary_is_exactly_300_unchanged_and_301_cut():
    assert MAX_LINE_CHARS == 300
    assert one_line("a" * 300) == "a" * 300
    assert one_line("a" * 301) == "a" * 300 + "…"
    assert one_line("a" * 5000) == "a" * 300 + "…"


def test_the_cap_applies_to_the_escaped_line_and_never_splits_a_token():
    out = one_line("\n" * 300)                    # each newline shows as an eight-character token
    assert len(out) <= MAX_LINE_CHARS + 1 and out.endswith("…")
    body = out[:-1]
    assert TOKEN.sub("", body) == "" and body.count("<U+") == len(body) // 8      # whole tokens only
    out2 = one_line("a" * 299 + "\n")              # the token would end at 307: it is not half written
    assert out2 == "a" * 299 + "…"


@pytest.mark.parametrize("ch, shown", [("\ud800", "<U+D800>"), ("\udfff", "<U+DFFF>"), ("\n", "<U+000A>")])
def test_unpaired_surrogates_and_line_breaks_are_shown_not_written(ch, shown):
    assert one_line(f"a{ch}b") == f"a{shown}b"


def test_the_pipe_is_escaped_only_when_asked():
    assert one_line("a|b") == "a|b"
    assert one_line("a|b", escape_pipe=True) == "a\\|b"
    assert len(one_line("|" * 400, escape_pipe=True)) <= MAX_LINE_CHARS + 1


# --- F-Q47-1: render_markdown ----------------------------------------------------------------------------------------

def test_render_markdown_keeps_agent_id_and_the_ledger_reason_on_one_line_and_in_one_cell():
    reason = "tampered\n\n## Fake heading\n\nSigner: Mallory | extra | cells"
    report = evaluate(_manifest(), agent_id="x\n\n## Injected\n\ntext",
                      sources=EvidenceSources(ledger_verify={"ok": False, "reason": reason}))
    md = render_markdown(report)
    assert len([ln for ln in md.splitlines() if ln.startswith("# ")]) == 1
    assert not re.search(r"(?m)^## (Injected|Fake heading)", md) and not re.search(r"(?m)^Signer: Mallory", md)
    (row,) = [ln for ln in md.splitlines() if "ledger verify failed" in ln]
    cells = re.split(r"(?<!\\)\|", row.strip())
    assert len(cells) == 8                         # leading and trailing empties plus the six columns
    assert "\\|" in row and "<U+000A>" in row


def test_post_crosswalk_markdown_gives_the_same_one_line_rendering():
    client = TestClient(create_app(stale_store=StaleStore()))
    r = client.post("/crosswalk/markdown", json={"manifest": _manifest(), "agent_id": "x\n\n## Injected\n\ntext"})
    assert r.status_code == 200, r.text
    assert not re.search(r"(?m)^## Injected", r.text) and "<U+000A>" in r.text


def test_an_unpaired_surrogate_in_agent_id_is_not_a_server_error_on_crosswalk_markdown():
    client = TestClient(create_app(stale_store=StaleStore()))
    r = client.post("/crosswalk/markdown", content='{"manifest": %s, "agent_id": "a\\ud800b"}' % __import__("json").dumps(_manifest()),
                    headers={"content-type": "application/json"})
    assert r.status_code == 200 and "<U+D800>" in r.text


# --- F-Q47-2: the staleness branch ------------------------------------------------------------------------------------

def test_a_staleness_entry_the_code_calls_unreachable_is_still_one_line():
    entry = {"framework": "nist-ai-rmf\n## Fake", "flagged_at": "2026-01-01\n## Fake2", "reason": "r\n\n## Fake3\n\nSigner: Mallory",
             "stale_window_seconds": 42}
    md, _ = generate_pack(_manifest(), signer="Don Hagell", stale_store=_Store(status_active=[entry]), agent_id="agent-1")
    assert not re.search(r"(?m)^## Fake", md) and not re.search(r"(?m)^Signer: Mallory", md)
    (line,) = [ln for ln in md.splitlines() if "framework: nist-ai-rmf" in ln]
    assert "reason: r<U+000A><U+000A>## Fake3" in line and "flagged_at: 2026-01-01<U+000A>" in line


# --- F-Q47-3: an unpaired surrogate in agent_id on POST /pack ---------------------------------------------------------

def test_an_unpaired_surrogate_in_agent_id_is_a_named_refusal_not_a_500_on_post_pack(tmp_path):
    client = TestClient(create_app(stale_store=StaleStore()))
    body = '{"signer": "Don Hagell", "manifest": %s, "agent_id": "a\\ud800b"}' % __import__("json").dumps(_manifest())
    r = client.post("/pack", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422, r.text
    assert "surrogate" in r.json()["detail"] and "\ud800" not in r.text and "ud800" not in r.text.lower()


def test_generate_pack_refuses_an_unpaired_surrogate_in_agent_id_by_name():
    with pytest.raises(ValueError, match="surrogate"):
        generate_pack(_manifest(), signer="Don Hagell", stale_store=_Store(), agent_id="a\udc00b")


# --- F-Q47-4 (c): an empty agent_id ---------------------------------------------------------------------------------

@pytest.mark.parametrize("agent_id", [None, ""])
def test_an_absent_or_empty_agent_id_reads_manifest_only(agent_id):
    md, _ = generate_pack(_manifest(), signer="Don Hagell", stale_store=_Store(), agent_id=agent_id)
    assert "- agent_id: manifest-only" in md.splitlines()


# --- F-Q47-5: the gap labels are on the right controls ----------------------------------------------------------------

def test_the_gap_labels_name_the_right_kind_of_gap_on_the_right_control():
    md, data = generate_pack(
        template_data("default"), signer="Don Hagell", stale_store=_Store(), agent_id="agent-1",
        sources=EvidenceSources(ledger_verify={"ok": False, "reason": "hash mismatch"}))
    controls = data["controls"]
    undeclared = [c["control_id"] for c in controls if not c["declared"]]
    unevidenced = [c["control_id"] for c in controls if c["evidenced"] is False]
    assert undeclared and unevidenced                     # the fixture exercises both kinds
    lines = md.splitlines()
    for cid in undeclared:
        assert any(ln.startswith(f"- {cid} — not declared:") for ln in lines), cid
    for cid in unevidenced:
        assert any(ln.startswith(f"- {cid} — not evidenced:") for ln in lines), cid
    for cid in set(undeclared) - set(unevidenced):
        assert not any(ln.startswith(f"- {cid} — not evidenced:") for ln in lines), cid
