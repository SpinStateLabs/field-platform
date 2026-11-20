"""C-1014 port, item (d) (reviewer F-C869-7): stale statements about the Tier 2 tools are pinned out of the docs. The check
reads the repository docs, so it is skipped in a copy of the service directory (the mutation check copies only that)."""
import pathlib

import pytest

ENV_DOC = pathlib.Path(__file__).resolve().parents[3] / "docs" / "ENVIRONMENT.md"
STALE = ("No Tier 2 tools exist in this build", "refuses to start in this build", "not in this build")


def test_the_environment_doc_does_not_say_there_are_no_tier2_tools():
    if not ENV_DOC.is_file():
        pytest.skip("docs/ENVIRONMENT.md is not part of this tree")
    row = next(line for line in ENV_DOC.read_text().splitlines() if line.startswith("| `FFMCP_ENABLE_WRITES`"))
    assert not any(w in row for w in STALE) and "7 Tier 2 tools" in row


def test_no_test_docstring_or_readme_says_the_write_entry_point_is_unavailable():
    here = pathlib.Path(__file__).resolve().parent
    for p in [*here.glob("test_*.py"), here.parent / "README.md"]:
        if p.name == "test_docs_wording.py":
            continue
        assert "refuses to start in this build" not in p.read_text(), p.name
