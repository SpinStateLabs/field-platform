"""Mutant survivors in render_markdown (Lane R): each section has a populated
branch and an explicit empty-state line. Existing tests only drove one side."""

from incident_replay.engine import (
    AuthorityGrant, PostMortem, TimelineEntry, render_markdown,
)


def _pm(**kw):
    base = dict(
        agent_id="a-1",
        window={"since": "2026-01-01T00:00:00+00:00", "until": "2026-01-02T00:00:00+00:00"},
        generated_at="2026-01-02T00:00:00+00:00",
        ledger_integrity_ok=True, ledger_integrity_detail="chain ok",
        ledger_integrity_status="intact",
        agent_record=None, authority=[], timeline=[], first_failure=None,
        counts={}, raci={},
    )
    base.update(kw)
    return PostMortem(**base)


def test_empty_sections_print_their_explicit_empty_state_and_nothing_else():
    md = render_markdown(_pm())
    assert "- ⚠ agent not found in registry" in md
    assert "- ⚠ no delegation grants overlapped this window" in md
    assert "- no ledger events for this agent in the window" in md
    # populated-branch markers must be absent
    assert "| Token | Granted by |" not in md
    assert "- Owner:" not in md
    assert "**tool.call**" not in md


def test_populated_sections_print_their_data_not_the_empty_state():
    pm = _pm(
        agent_record={"agent_id": "a-1", "name": "Alpha", "owner": "Owner P",
                      "domain": "finance", "status": "active", "manifest_ref": None},
        authority=[AuthorityGrant(
            token_id="abcdef0123456789", granted_by="Grantor P", scope=["read x"],
            issued_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-03T00:00:00+00:00", revoked=False)],
        timeline=[TimelineEntry(ts="2026-01-01T10:00:00+00:00",
                                event_type="tool.call", summary="did a thing",
                                hash="h1")],
    )
    md = render_markdown(pm)
    assert "agent not found in registry" not in md
    assert "no delegation grants overlapped" not in md
    assert "no ledger events for this agent" not in md
    assert "- **a-1** — Alpha" in md
    assert "- Owner: Owner P · Domain: finance · Status: active" in md
    # a missing manifest_ref prints the literal placeholder, not the falsy value
    assert "- Manifest: `<none>`" in md
    assert "| `abcdef01…` | Grantor P | read x |" in md
    assert "- `2026-01-01T10:00:00` **tool.call** — did a thing" in md


def test_a_set_manifest_ref_is_printed_verbatim():
    pm = _pm(agent_record={"agent_id": "a-1", "name": "Alpha", "owner": "O",
                           "domain": "d", "status": "active",
                           "manifest_ref": "manifests/a-1.yaml"})
    assert "- Manifest: `manifests/a-1.yaml`" in render_markdown(pm)
