"""v1.2-deploy-rollback.md names the code behind five trust-table rows by file
and symbol, not line number (scout S-D2: the old cites had drifted). Pin that
the line cites are gone and that every named symbol still exists in its file."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = (ROOT / "docs/runbooks/v1.2-deploy-rollback.md").read_text(encoding="utf-8")

# (cite as written in the runbook, file, symbols that must exist as defs)
CITES = [
    ("lifecycle_manager/api.py", "services/lifecycle-manager/src/lifecycle_manager/api.py",
     ["delegation_client", "killswitch_client"]),
    ("estate_probe.py", "tools/estate_probe.py", ["cmd_catalogue", "_catalogue_run", "operator_pair"]),
    ("renew_token.py", "tools/renew_token.py", ["operator_pair"]),
    ("provision_ssl_agents.py", "tools/provision_ssl_agents.py", ["operator_pair"]),
]


def test_no_line_cites_for_these_files():
    for cite, _, _ in CITES:
        assert not re.search(re.escape(cite) + r"`?:\d+", RUNBOOK), cite
    assert not re.search(r"lifecycle_manager/api\.py:\d+", RUNBOOK)


def test_named_symbols_exist():
    for cite, path, symbols in CITES:
        assert cite in RUNBOOK, cite
        text = (ROOT / path).read_text(encoding="utf-8")
        for name in symbols:
            assert re.search(rf"^def {name}\(", text, re.M), (path, name)
