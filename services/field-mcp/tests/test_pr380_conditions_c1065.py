"""C-1065: reviewer C-1057 conditions on PR 380. One section per finding; each test fails without its fix.

Mutants (scripts/mutants.py): HF1 the header-safety check on the operator pair and the service keys removed; SG1 the
caller signer not handed to the audit; ID1 the agent id of `check` / `crossing` unbounded; ID2 top-level string
arguments of Tier 2 tools unbounded; SU1 the encodability check before the intent removed; SU2 the outcome row for an
error after the intent removed; U5 a 5xx on a write reported as a plain status; RZ1 the Zl and Zp separators kept;
RZ2 the visually blank filler characters kept.
"""
import json

import pytest

from conftest import KEY, Stub
from field_mcp import audit as au, client as cl
from field_mcp.catalog import SERVICES
from field_mcp.config import Config, ConfigError, ServiceConfig, load
from field_mcp.server import build_dispatcher
from field_mcp.tools import Dispatcher, build_specs

OP, OPKEY = "op-alice", "opkey-" + "Z9q2" * 4
W_ENV = {"FFMCP_ENABLE_WRITES": "1", "FFMCP_SEALED_LEDGER_URL": "http://127.0.0.1:1",
         "FFMCP_OPERATOR": OP, "FFMCP_OPERATOR_KEY": OPKEY}


@pytest.fixture
def two():
    target, ledger = Stub(), Stub()
    ledger.routes[("POST", "/events")] = (201, {"event_id": 1}, {})
    yield target, ledger
    target.close()
    ledger.close()


def write_disp(target, ledger, **kw):
    svcs = {s: ServiceConfig(target.base, KEY) for s in SERVICES}
    svcs["sealed-ledger"] = ServiceConfig(ledger.base, KEY)
    cfg = Config(tier=2, services=svcs, operator=OP, operator_key=OPKEY, **kw)
    ups = {s: cl.Upstream(s, c.base, c.key) for s, c in svcs.items()}
    return Dispatcher(cfg, ups, au.Audit(ups["sealed-ledger"], OP, "test-client"))


REGISTER = {"body": {"agent_id": "agent-1", "name": "A", "owner": "o"}, "reason": "onboarding agent-1"}
CHECK = {"body": {"agent_id": "agent-1", "action": "draft invoices"}, "reason": "dry run of a verdict"}


# ---- F-C1057-380-1: a header-unsafe character in a credential is refused at startup, naming the variable ------------

UNSAFE = ["k\n", "k\r\n", "k\t", "k\x00", "k\x7f", "kéy", "k "]


@pytest.mark.parametrize("bad", UNSAFE)
@pytest.mark.parametrize("var", ["FFMCP_OPERATOR", "FFMCP_OPERATOR_KEY", "FFMCP_AGENT_REGISTRY_KEY", "FFMCP_SEALED_LEDGER_KEY"])
def test_a_header_unsafe_character_in_a_credential_stops_the_write_process(var, bad):
    env = {**W_ENV, "FFMCP_AGENT_REGISTRY_URL": "http://127.0.0.1:2", var: bad}
    with pytest.raises(ConfigError) as e:
        load(2, env)
    assert var in str(e.value) and "Zq7" not in str(e.value)


def test_a_header_safe_credential_with_an_inner_space_and_punctuation_still_loads():
    cfg = load(2, {**W_ENV, "FFMCP_OPERATOR": "op alice", "FFMCP_OPERATOR_KEY": "k-._~+/=:;,@!#$%&*()[]{}<>|^`'\\\"?"})
    assert cfg.operator == "op alice"


def test_the_read_process_is_not_changed_by_the_check():
    assert load(1, {"FFMCP_AGENT_REGISTRY_URL": "http://127.0.0.1:2", "FFMCP_AGENT_REGISTRY_KEY": "k\n"}).tier == 1
