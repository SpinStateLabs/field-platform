"""Scout S-2-8: `home_org()` and the documented blank `FIELD_ORG_NAME` behaviour were untested (docs/ENVIRONMENT.md:
"any string, used as read (a blank value is blank)"). Tests only; no source change.

What is pinned is what the code does today, including its sharp edge: only an UNSET variable falls back to the default.
A blank value is used as read, so `/health` reports an empty home org, every inbound crossing is refused at F.peer
(an empty needle matches nothing, the guard in `_lists_org`), and an outbound verdict is attributed to '/<agent>'."""
from __future__ import annotations

import pytest

from federation_broker.engine import DEFAULT_HOME_ORG, HOME_ORG_ENV, _lists_org, home_org
from test_federation_broker import (COUNTERPARTY, counterparty_manifest, crossing, signed_crossing,  # noqa: F401
                                    stack)
from test_federation_outbound import OUR_AGENT, our_manifest, outbound


def test_the_variable_name_and_default_are_the_documented_ones():
    assert HOME_ORG_ENV == "FIELD_ORG_NAME"
    assert DEFAULT_HOME_ORG == "Spin State Labs"


def test_unset_gives_the_default(monkeypatch):
    monkeypatch.delenv(HOME_ORG_ENV, raising=False)
    assert home_org() == "Spin State Labs"


def test_set_gives_that_value_as_read(monkeypatch):
    monkeypatch.setenv(HOME_ORG_ENV, "Acme Holdings Ltd")
    assert home_org() == "Acme Holdings Ltd"
    monkeypatch.setenv(HOME_ORG_ENV, "  Padded Org  ")
    assert home_org() == "  Padded Org  "          # not stripped


def test_an_empty_value_is_empty_not_the_default(monkeypatch):
    monkeypatch.setenv(HOME_ORG_ENV, "")
    assert home_org() == ""


@pytest.mark.parametrize("blank", ["   ", "\t", " \n "])
def test_a_whitespace_only_value_is_returned_verbatim_not_collapsed_to_empty(monkeypatch, blank):
    """The card expected '' here; the code returns the raw string. Pinned as it is."""
    monkeypatch.setenv(HOME_ORG_ENV, blank)
    assert home_org() == blank


@pytest.mark.parametrize("blank", ["", "   ", "\t", " "])
def test_a_blank_home_org_matches_no_peer_at_all(blank):
    peers = [{"org": "Spin State Labs"}, {"org": ""}, {"org": "   "}, {"org": "anything"}]
    assert _lists_org(peers, blank) is False


def test_health_reports_the_home_org_as_set(stack, monkeypatch):
    broker, _ = stack
    monkeypatch.setenv(HOME_ORG_ENV, "Acme Holdings Ltd")
    assert broker.get("/health").json()["home_org"] == "Acme Holdings Ltd"


def test_health_reports_an_empty_home_org_when_the_variable_is_empty(stack, monkeypatch):
    broker, _ = stack
    monkeypatch.setenv(HOME_ORG_ENV, "")
    body = broker.get("/health").json()
    assert body["ok"] is True and body["home_org"] == ""


def test_health_reports_the_default_when_the_variable_is_unset(stack, monkeypatch):
    broker, _ = stack
    monkeypatch.delenv(HOME_ORG_ENV, raising=False)
    assert broker.get("/health").json()["home_org"] == "Spin State Labs"


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("peer_org", ["Spin State Labs", "", "   ", "Borealis Example Corp"])
def test_a_blank_home_org_blocks_every_inbound_crossing_at_f_peer(stack, monkeypatch, blank, peer_org):
    """Whatever org the presented manifest lists as an allowed peer, including the real home org, an empty name and a
    whitespace-only name: the blank home org never matches, so nothing crosses inbound."""
    broker, _ = stack
    monkeypatch.setenv(HOME_ORG_ENV, blank)
    manifest = counterparty_manifest()
    manifest["federated"]["allowed_peers"] = [
        {"agent_id": "invoicing-agent", "org": peer_org, "trust_basis": "federation contract FED-2026-001 (demo)"}]
    verdict = crossing(broker, manifest=manifest).json()
    assert verdict["decision"] == "BLOCK" and verdict["clause_id"] == "F.peer"
    assert verdict["context"]["home_org"] == blank


def test_the_f_peer_reason_for_a_blank_home_org_names_nobody(stack, monkeypatch):
    """The text reads 'does not list  as an allowed peer' with an empty name (two spaces): pinned, and flagged in the PR."""
    broker, _ = stack
    monkeypatch.setenv(HOME_ORG_ENV, "")
    verdict = crossing(broker).json()
    assert verdict["reasons"] == ["counterparty manifest does not list  as an allowed peer"]


def test_the_default_home_org_still_lets_a_signed_inbound_crossing_through(stack, monkeypatch):
    """Control: the same request under the real home org is ALLOWED, so the blank-home-org blocks above are caused by
    the blank value and by nothing else in the request."""
    broker, _ = stack
    monkeypatch.delenv(HOME_ORG_ENV, raising=False)
    verdict = signed_crossing(broker).json()
    assert verdict["decision"] == "ALLOW"


def test_an_outbound_verdict_names_our_agent_under_the_home_org(stack, monkeypatch):
    broker, _ = stack
    monkeypatch.setenv(HOME_ORG_ENV, "Spin State Labs")
    verdict = outbound(broker).json()
    assert verdict["decision"] == "ALLOW"
    assert verdict["agent_id"] == f"Spin State Labs/{OUR_AGENT}"
    assert verdict["context"]["home_org"] == "Spin State Labs"


def test_an_outbound_verdict_under_a_blank_home_org_is_attributed_to_a_bare_slash_agent(stack, monkeypatch):
    broker, _ = stack
    monkeypatch.setenv(HOME_ORG_ENV, "")
    verdict = outbound(broker).json()
    assert verdict["agent_id"] == f"/{OUR_AGENT}"
    assert verdict["context"]["home_org"] == ""
