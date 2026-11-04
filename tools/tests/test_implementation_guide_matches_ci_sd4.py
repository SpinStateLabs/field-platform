"""docs/IMPLEMENTATION.md section 2 (install and verify) calls ci.yml authoritative, so
every install and test command of the CI `tests` job must appear in it, or the guide must
say it is a subset (scout S-D4). It stopped at field-agent and the services: no
defence-shield install, no `tools/tests`, no retro tests."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs" / "IMPLEMENTATION.md").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _section2() -> str:
    m = re.search(r"^##\s+2\b.*?(?=^##\s+\d)", GUIDE, re.S | re.M)
    assert m, "docs/IMPLEMENTATION.md has no section 2"
    return m.group(0)


def test_ci_installs_the_retro_package_and_runs_its_tests_and_the_tools_tests():
    # the premise: if CI stops doing these, this pin should be revisited, not silently pass
    assert 'pip install $C --no-deps -e "defence-shield/agent-incident-retro"' in CI
    assert "(cd defence-shield/agent-incident-retro && python -m pytest -q tests)" in CI
    assert "run: pytest -q tools/tests" in CI


@pytest.mark.parametrize("needle", [
    'pip install --no-deps -e "defence-shield/agent-incident-retro"',
    "(cd defence-shield/agent-incident-retro && python -m pytest -q tests)",
    "pytest -q tools/tests",
])
def test_section_2_has_the_command(needle):
    assert needle in _section2(), f"section 2 of IMPLEMENTATION.md lacks: {needle}"


def test_section_2_says_it_is_a_subset_and_names_the_ci_only_gates():
    text = _section2().lower()
    assert "subset" in text
    for gate in ("topology", "anchors", "verify_sync"):
        assert gate in text, f"the subset note does not name the CI-only gate: {gate}"


def test_the_guide_still_calls_ci_authoritative():
    assert "authoritative list is the test steps of `.github/workflows/ci.yml`" in _section2()
