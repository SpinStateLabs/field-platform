"""The README '## CLI' code block lists exactly the verbs cli.app registers (S9-13): none missing, none invented."""
from __future__ import annotations

import re
from pathlib import Path

from spend_governor import cli

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def _block() -> str:
    section = README.split("\n## CLI\n", 1)[1]
    return re.search(r"```\n(.*?)\n```", section, re.S).group(1)


def _registered() -> set[str]:
    return {c.name or c.callback.__name__.replace("_", "-") for c in cli.app.registered_commands}


def _documented() -> set[str]:
    return {m.group(1) for m in re.finditer(r"^governor ([a-z][a-z-]*)", _block(), re.M)}


def test_every_registered_verb_is_in_the_readme_cli_block():
    assert _registered() - _documented() == set()


def test_the_readme_cli_block_has_no_verb_the_app_lacks():
    assert _documented() - _registered() == set()


def test_the_known_verbs_are_all_seen():
    # guards the enumeration itself: an empty set on both sides would pass the two tests above
    assert {"set-cap", "spend", "status", "rate-limits", "usage", "set-policy", "escalations", "resolve", "serve"} <= _registered()


def test_the_readme_states_the_real_exit_codes():
    assert "exit 1 on BLOCK" in _block() and "exit 3 on a rogue finding" in _block()
