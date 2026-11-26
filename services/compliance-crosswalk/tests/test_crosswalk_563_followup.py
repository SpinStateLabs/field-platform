"""Supersedes PR 563 (with PR 1164): what PR 563 carried that main and #1164 did not.

F-Q47-3  an unpaired surrogate (Cs) cannot be encoded as UTF-8, so shown text carrying one was a server error or a
         pack that could not be written: one_line now shows it as a space, the signer refuses it (it is a refused
         category), and generate_pack refuses an agent_id holding one by name.
F-Q47-2  the pack's staleness entries on the branch the code calls unreachable are one line each, also for a flag
         stored before staleness cleaned reasons at mark time or read from a hand-edited store."""

from __future__ import annotations

import re

import pytest

from compliance_crosswalk.engine import EvidenceSources, evaluate, one_line, render_markdown
from compliance_crosswalk.evidence_pack import InvalidSigner, generate_pack
from tests.test_signer_sanitise_c252 import FakeStore, resolved_manifest


class StatusOnlyStore(FakeStore):
    """active() is empty but status() lists a flag: the branch generate_pack calls unreachable."""

    def __init__(self, entry):
        self.entry = entry

    def status(self):
        return {"corpus_version": self.corpus_version, "active": [self.entry], "history": []}


def test_one_line_shows_an_unpaired_surrogate_as_a_space():
    assert one_line("a\ud800b\udc00c") == "a b c"


def test_a_ledger_reason_with_an_unpaired_surrogate_renders_and_encodes():
    md = render_markdown(evaluate(resolved_manifest(), sources=EvidenceSources(ledger_verify={"ok": False, "reason": "x\ud800y"})))
    md.encode("utf-8")                                    # was a UnicodeEncodeError
    assert "x y" in md


def test_generate_pack_refuses_an_unpaired_surrogate_in_agent_id_by_name():
    with pytest.raises(ValueError, match="surrogate") as e:
        generate_pack(resolved_manifest(), signer="Ann Lee", stale_store=FakeStore(), agent_id="a\udc00b")
    assert "\udc00" not in str(e.value)


def test_a_signer_with_an_unpaired_surrogate_is_refused():
    with pytest.raises(InvalidSigner, match=r"U\+D800"):
        generate_pack(resolved_manifest(), signer="Ann\ud800Lee", stale_store=FakeStore())


def test_a_staleness_entry_the_code_calls_unreachable_is_still_one_line():
    entry = {"framework": "nist-ai-rmf\n## Fake", "flagged_at": "2026-01-01\n## Fake2",
             "reason": "r\n\n## Fake3\n\nSigner: Mallory", "stale_window_seconds": 42}
    md, _ = generate_pack(resolved_manifest(), signer="Ann Lee", stale_store=StatusOnlyStore(entry), agent_id="agent-1")
    assert not re.search(r"(?m)^## Fake", md) and not re.search(r"(?m)^Signer: Mallory", md)
    (line,) = [ln for ln in md.splitlines() if "framework: nist-ai-rmf" in ln]
    assert "reason: r ## Fake3 Signer: Mallory" in line and "flagged_at: 2026-01-01 ## Fake2" in line
    md.encode("utf-8")
