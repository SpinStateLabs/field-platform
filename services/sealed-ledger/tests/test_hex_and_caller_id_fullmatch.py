"""S6-9: ``^...$`` with ``re.match`` accepts a trailing newline. A witness ``head_hash`` of 64 hex plus ``\\n`` (or
``\\r\\n``) was returned by ``parse_head`` and would have been written into an ``anchor.remote`` event, and a caller id
``a-1\\n`` built the path ``a-1\\n.pub.pem``. Both are ``fullmatch`` now (same class as S3-17 / S5-5)."""

from __future__ import annotations

import json

import pytest

from sealed_ledger.store import CallerKeyring
from sealed_ledger.witness import WitnessError, check_anchor, parse_head

HEX = "ab" * 32


def body(head):
    return json.dumps({"event_count": 3, "head_hash": head}).encode()


# ---- parse_head -------------------------------------------------------------------------------------------------------

def test_a_clean_head_is_returned():
    assert parse_head(body(HEX)) == (3, HEX)


@pytest.mark.parametrize("bad", [HEX + "\n", HEX + "\r\n", HEX + "\r", "\n" + HEX, HEX + " ", HEX[:-1], HEX + "a",
                                 HEX.upper(), "", HEX + "\n\n", HEX + "\x00"], ids=repr)
def test_parse_head_refuses_anything_but_exactly_64_lowercase_hex(bad):
    with pytest.raises(WitnessError, match="64 lowercase hex"):
        parse_head(body(bad))


# ---- check_anchor -----------------------------------------------------------------------------------------------------

class NoSnap:
    """a malformed anchor is refused before the snapshot is read"""

    def __getattr__(self, name):
        raise AssertionError(f"snapshot read ({name}) for a malformed anchor")


@pytest.mark.parametrize("bad", [HEX + "\n", HEX + "\r\n", "\n" + HEX, HEX + " ", HEX.upper()], ids=repr)
def test_check_anchor_calls_a_newline_padded_head_malformed(bad):
    reason = check_anchor({"length": 3, "head_hash": bad}, NoSnap(), 10, None, None)
    assert reason == "malformed: head_hash is not 64 lowercase hex"


def test_check_anchor_still_gets_past_the_malformed_gate_for_a_clean_head():
    class Snap:
        def hash_at(self, i):
            return HEX
    assert check_anchor({"length": 3, "head_hash": HEX}, Snap(), 10, None, None) is None


# ---- the caller keyring -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("good", ["a", "agent-1", "a" * 63, "0abc", "a-b-c"])
def test_a_valid_caller_id_builds_its_key_path(tmp_path, good):
    assert CallerKeyring(tmp_path).path_for(good) == tmp_path / f"{good}.pub.pem"


@pytest.mark.parametrize("bad", ["a-1\n", "agent-1\r\n", "a-1\r", "\na-1", "a-1 ", "A-1", "-a", "a" * 64, "", "a/b",
                                 "a-1\x00", None, 5], ids=repr)
def test_an_id_outside_the_name_rule_has_no_path(tmp_path, bad):
    assert CallerKeyring(tmp_path).path_for(bad) is None


def test_an_unknown_newline_id_is_refused_without_building_a_path(tmp_path):
    from sealed_ledger.store import CallerRefused
    (tmp_path / "a-1.pub.pem").write_text("not a key")
    with pytest.raises(CallerRefused):
        CallerKeyring(tmp_path).public_pem("a-1\n")
