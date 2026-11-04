"""Service README claims pinned to the code (docs drift card).

(1) No services/*/README.md cites code as `file.py:123` (a line number moves with every edit; four such
    cites had already drifted: lifecycle-manager `create_app` / `GET /findings`, sealed-ledger
    `witness_run`). Cite the symbol.
(2) Defaults the READMEs state for environment variables equal the constant or literal in the code.
(3) The lifecycle-manager README's `FIELD_LIFECYCLE_EVERY` rules match `create_app` and `serve`.
Each check reads the README and the source text; nothing is imported or run.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SVC = ROOT / "services"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_service_readmes_cite_symbols_not_line_numbers() -> None:
    bad = []
    for readme in sorted(SVC.glob("*/README.md")):
        for n, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"[\w/.-]+\.(?:py|sh|yml|yaml|toml|html):\d+(?:-\d+)?", line):
                bad.append(f"{readme.relative_to(ROOT)}:{n}: {m.group(0)}")
    assert not bad, "line-number cites (cite the symbol): " + "; ".join(bad)


# (readme, README regex that must match, code file, code regex that must match)
DEFAULTS = [
    ("services/claude-approver/README.md", r"CLAUDE_APPROVER_POLL_SECONDS`, default 2 s",
     "services/claude-approver/src/claude_approver/config.py", r"^DEFAULT_POLL_SECONDS = 2\.0$"),
    ("services/claude-approver/README.md", r"CLAUDE_APPROVER_POLL_SECONDS` \| default 2\.0, floor 0\.5",
     "services/claude-approver/src/claude_approver/config.py", r"^MIN_POLL_SECONDS = 0\.5$"),
    ("services/claude-approver/README.md", r"CLAUDE_APPROVER_HALT_WAIT_SECONDS` \| default 20 ",
     "services/claude-approver/src/claude_approver/config.py", r"^DEFAULT_HALT_WAIT_SECONDS = 20\.0$"),
    ("services/claude-approver/README.md", r"default `/run/claude-approver/api-key`",
     "services/claude-approver/src/claude_approver/config.py",
     r'^DEFAULT_KEY_FILE = "/run/claude-approver/api-key"$'),
    ("services/federation-broker/README.md", r'FIELD_ORG_NAME` \(default "Spin State Labs"\)',
     "services/federation-broker/src/federation_broker/engine.py", r'^DEFAULT_HOME_ORG = "Spin State Labs"$'),
    ("services/force-gateway/README.md", r"FORCE_TELEMETRY_WINDOW`, default 50",
     "services/force-gateway/src/force_gateway/api.py", r"^DEFAULT_TELEMETRY_WINDOW = 50$"),
    ("services/force-gateway/README.md", r"FORCE_GATEWAY_SENTINEL_TIMEOUT` \(default \*\*30 s\*\*",
     "services/force-gateway/src/force_gateway/api.py", r"^DEFAULT_SENTINEL_TIMEOUT = 30\.0$"),
    ("services/force-gateway/README.md", r"FORCE_GATEWAY_SAMPLE_EVERY`, default 10, 0=off",
     "services/force-gateway/src/force_gateway/hygiene_judge.py", r"def resolve_sample_every\(default: int = 10\)"),
    ("services/force-gateway/README.md", r"FORCE_HYGIENE_WINDOW`, default 5",
     "services/force-gateway/src/force_gateway/api.py", r'os\.environ\.get\("FORCE_HYGIENE_WINDOW", "5"\)'),
    ("services/conformance-sentinel/README.md", r"FIELD_JUDGE_CONFIDENCE_FLOOR`, default 0\.8",
     "services/conformance-sentinel/src/conformance_sentinel/judge.py", r"def resolve_floor\(default: float = 0\.8\)"),
    ("services/conformance-sentinel/README.md", r"FIELD_JUDGE_MODEL` \(default `claude-sonnet-5`\)",
     "services/conformance-sentinel/src/conformance_sentinel/judge.py",
     r'^JUDGE_MODEL_DEFAULT = "claude-sonnet-5"$'),
    ("services/ops-console/README.md", r"FIELD_CONSOLE_MAX_STREAMS`, default 8",
     "services/ops-console/src/ops_console/api.py", r'os\.environ\.get\("FIELD_CONSOLE_MAX_STREAMS", "8"\)'),
    ("services/sealed-ledger/README.md", r"`ledger witness run --every` option \(default 3600,\nminimum 1;",
     "services/sealed-ledger/src/sealed_ledger/cli.py", r'"--every", min=1'),
    ("services/sealed-ledger/README.md", r"default 3600\)",
     "integration/demo/docker-compose.gb10.yml", r"--every \$\{FIELD_WITNESS_EVERY:-3600\}"),
    ("services/lifecycle-manager/README.md", r"`FIELD_LIFECYCLE_EVERY` is\n`86400`",
     "integration/demo/docker-compose.yml", r"FIELD_LIFECYCLE_EVERY: \$\{FIELD_LIFECYCLE_EVERY:-86400\}"),
    ("services/lifecycle-manager/README.md", r"`86400` \(the `FIELD_LIFECYCLE_EVERY` default",
     "integration/fly/entrypoint.sh", r'FIELD_LIFECYCLE_EVERY="\$\{FIELD_LIFECYCLE_EVERY:-86400\}"'),
]


@pytest.mark.parametrize("readme,readme_re,code,code_re", DEFAULTS)
def test_readme_default_matches_code(readme: str, readme_re: str, code: str, code_re: str) -> None:
    assert re.search(readme_re, read(readme)), f"{readme} no longer states {readme_re!r}"
    assert re.search(code_re, read(code), re.M), f"{code} no longer has {code_re!r}: update {readme}"


def test_lifecycle_every_rules_match_create_app_and_serve() -> None:
    readme = read("services/lifecycle-manager/README.md")
    api = read("services/lifecycle-manager/src/lifecycle_manager/api.py")
    cli = read("services/lifecycle-manager/src/lifecycle_manager/cli.py")
    # README: a negative integer is clamped to 0; the env fallback turns a non-digit into 0
    assert "a negative\n  integer is accepted and clamped to `0`" in readme
    assert re.search(r"every = int\(raw\) if raw\.isdigit\(\) else 0", api)
    assert re.search(r"if every < 0:\n\s+every = 0", api)
    # README: `serve` parses --every as an integer option and hands it to create_app
    assert re.search(r'every: int = typer\.Option\(\s*0,\s*"--every"', cli)
    assert re.search(r"create_app\(roster_path=roster, every=every", cli)
    # README: GET /findings answers 404 carrying last_tick before any sweep
    assert re.search(r'"last_tick": tick', api)
