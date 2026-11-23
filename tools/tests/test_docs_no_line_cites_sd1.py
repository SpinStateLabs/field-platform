"""docs/ARCHITECTURE.md and docs/IMPLEMENTATION.md cite code by file and symbol,
never by line number: about half of the cites there had drifted (scout S-D1;
read against main: ci.yml, agent_registry/api.py, ops_console/api.py and most
force_gateway/api.py cites were off), and no check watches them. docs/ENVIRONMENT.md keeps
its numbered anchors because tools/environment_anchors.py verifies those.

S12-30: the same rule now covers docs/INTEGRATION.md and every docs/runbooks/*.md (their file:line cites had drifted too:
`alerts.py:235` for a symbol defined at :256, `sealed_ledger/api.py:326` for a call the ledger no longer makes).
docs/DOSSIER.md stays out. Only the file:line form is checked there: a runbook names ports (`:8080`) in backticks, which
are not line cites, so the bare `:N` form stays a check of the two architecture documents."""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
LINE_CITE = re.compile(r"\.(?:py|yml|yaml|sh|toml|md|html):\d+")
BARE_LINE = re.compile(r"`:\d+(?:-\d+)?`|`:\d+`")


def test_no_file_line_cites():
    bad = []
    for name in ("ARCHITECTURE.md", "IMPLEMENTATION.md"):
        for n, line in enumerate((DOCS / name).read_text(encoding="utf-8").splitlines(), 1):
            if LINE_CITE.search(line) or BARE_LINE.search(line):
                bad.append(f"{name}:{n}")
    assert not bad, f"cite a symbol, not a line: {bad}"


def test_no_file_line_cites_in_integration_and_the_runbooks():
    bad = []
    for path in (DOCS / "INTEGRATION.md", *sorted((DOCS / "runbooks").glob("*.md"))):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if LINE_CITE.search(line):
                bad.append(f"{path.relative_to(DOCS)}:{n}")
    assert not bad, f"cite a symbol, not a line: {bad}"


def test_the_runbook_glob_finds_the_runbooks():
    names = {p.name for p in (DOCS / "runbooks").glob("*.md")}
    assert {"ntfy-alerts.md", "v1.2-deploy-rollback.md"} <= names


def test_a_port_is_not_a_line_cite():
    assert not LINE_CITE.search("the `:8080` site and `FIELD_REGISTRY_URL` at `:8001`")


def test_the_two_stale_cites_the_scout_found_are_gone():
    runbook = (DOCS / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    assert "sealed_ledger/api.py:326" not in runbook
    assert "alerts.py:235" not in (DOCS / "runbooks" / "ntfy-alerts.md").read_text(encoding="utf-8")


def test_the_check_sees_a_cite():
    assert LINE_CITE.search("`services/x/api.py:187`")
    assert BARE_LINE.search("at `:235`")
