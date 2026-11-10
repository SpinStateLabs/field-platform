"""S4-20: the agents docs do not claim both estates run pre-v1.2 kill-switch images; they point at the dated STATE.md record."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ["agents/README.md", "agents/ssl-invoicing-agent/SKILL.md", "agents/ssl-timekeeping-agent/SKILL.md"]


@pytest.mark.parametrize("rel", DOCS)
def test_no_stale_pre_v1_2_estate_claim(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "run pre-v1.2" not in text
    assert "until Don redeploys" not in text
    assert "2026-09-12" in text and "STATE.md" in text
    assert "NOT SUPPORTED" in text           # the 404/405 fallback stays described


def test_the_dated_source_the_docs_cite_exists():
    state = (ROOT / "STATE.md").read_bytes().decode("utf-8", "replace")
    assert "X0 — GB10 step, 2026-09-12" in state and "X0 — Fly step, 2026-09-12" in state


def test_the_probe_check_the_docs_name_exists():
    assert "B3 POST check-in records last_seen" in (ROOT / "tools/estate_probe.py").read_text(encoding="utf-8")


def test_the_fallback_branch_the_docs_describe_exists():
    assert "NOT SUPPORTED" in (ROOT / "tools/field-rest.ps1").read_text(encoding="utf-8")
