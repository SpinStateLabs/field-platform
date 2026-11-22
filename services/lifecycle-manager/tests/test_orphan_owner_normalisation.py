"""S12-14: the orphan test and the roster compare owners through ONE key (NFC, strip, casefold); matching is still
exact otherwise (no substring)."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone

import pytest

from lifecycle_manager.engine import LifecycleEngine, owner_key

NOW = datetime.now(timezone.utc).replace(microsecond=0)


class _Registry:
    def __init__(self, agents):
        self._agents = agents

    def list_agents(self):
        return [dict(a) for a in self._agents]


class _NoTokens:
    def get(self, path):
        return []


class _Ledger:
    def append(self, event_type, payload=None, agent_id=None):
        return None


def _agent(agent_id, owner):
    return {"agent_id": agent_id, "owner": owner, "status": "active", "created_at": NOW.isoformat()}


def _sweep(roster, *owners):
    agents = [_agent(f"a{i}", o) for i, o in enumerate(owners)]
    report = LifecycleEngine(registry=_Registry(agents), delegation=_NoTokens(), ledger=_Ledger()).sweep(roster, now=NOW)
    return report, [o.agent_id for o in report.orphans]


def test_owner_key_is_nfc_strip_casefold():
    assert owner_key("  Don Hagell ") == "don hagell"
    assert owner_key(unicodedata.normalize("NFD", "Zoë")) == owner_key(unicodedata.normalize("NFC", "ZOË"))
    assert owner_key("STRASSE") == owner_key("strasse") == owner_key("straße")


def test_a_padded_owner_is_not_an_orphan():
    _, orphans = _sweep("owner\nDon Hagell\n", "Don Hagell ", "\tdon hagell\n")
    assert orphans == []


@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_nfd_and_nfc_owners_match_either_roster_form(form):
    roster = "owner\n" + unicodedata.normalize(form, "Zoë Müller") + "\n"
    other = "NFD" if form == "NFC" else "NFC"
    _, orphans = _sweep(roster, unicodedata.normalize(other, "Zoë Müller"))
    assert orphans == []


def test_casefold_variants_are_not_orphans():
    _, orphans = _sweep("owner\nstrasse\n", "STRASSE", "Straße")
    assert orphans == []


def test_a_genuinely_different_owner_is_still_an_orphan():
    _, orphans = _sweep("owner\nDon Hagell\n", "Don Hagell Jr", "Hagell", "Someone Else")
    assert orphans == ["a0", "a1", "a2"]


def test_an_alias_still_matches_and_roster_size_counts_humans():
    report, orphans = _sweep('owner,aliases\nDon Hagell,"Don Hagell, Spin State Labs;DH"\n',
                             "Don Hagell, Spin State Labs ", "dh")
    assert orphans == []
    assert report.roster_size == 1
