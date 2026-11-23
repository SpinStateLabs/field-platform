"""S5-2: a roster that is not valid UTF-8, or whose path holds a NUL, is a DoaRosterError (503 at the mint), never an escaping
UnicodeDecodeError / ValueError. The message never quotes file bytes."""
from __future__ import annotations

import pytest

from delegation_authority.doa import DoaRosterError, load_roster
from test_doa_roster import spine  # noqa: F401  (fixture)

MARK = b"SYNTHETIC-MARKER-0123"


@pytest.mark.parametrize("payload", [
    b"\xff\xfe\x00grantors: []\n",
    MARK + b"\xff\xff",
    b"grantors:\n  - grantor: \xc3\x28\n",            # an invalid two-byte sequence
    b"\x80",
], ids=["utf16-bom", "marker-then-0xff", "bad-sequence", "lone-continuation"])
def test_non_utf8_roster_is_a_roster_error(tmp_path, payload):
    p = tmp_path / "doa-roster.yaml"
    p.write_bytes(payload)
    with pytest.raises(DoaRosterError) as e:
        load_roster(p)
    assert MARK.decode() not in str(e.value)
    assert "UnicodeDecodeError" in str(e.value)
    assert "not readable as UTF-8" in str(e.value)


def test_a_nul_in_the_path_is_a_roster_error():
    with pytest.raises(DoaRosterError) as e:
        load_roster("roster\x00.yaml")
    assert "ValueError" in str(e.value)
    assert "roster\x00" not in str(e.value)


def test_existing_refusals_are_unchanged(tmp_path):
    with pytest.raises(DoaRosterError, match="is unreadable"):
        load_roster(tmp_path / "missing.yaml")
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")
    with pytest.raises(DoaRosterError, match="is empty"):
        load_roster(p)


def test_a_good_roster_still_loads(tmp_path):
    p = tmp_path / "ok.yaml"
    p.write_text("grantors:\n  - grantor: Don\n    allowed_scope: [a]\n    max_ttl_days: 5\n    active: true\n", encoding="utf-8")
    assert load_roster(p).find("Don") is not None


def test_mint_under_a_non_utf8_roster_is_503_and_nothing_is_persisted(spine, tmp_path, monkeypatch):  # noqa: F811
    path = tmp_path / "doa-roster.yaml"
    path.write_bytes(MARK + b"\xff")
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(path))
    r = spine.mint()
    assert r.status_code == 503
    assert "refusing to mint" in r.json()["detail"]
    assert MARK.decode() not in r.text
    assert spine.delegation.get("/tokens").json() == []
    assert spine.ledger.get("/events").json() == []
