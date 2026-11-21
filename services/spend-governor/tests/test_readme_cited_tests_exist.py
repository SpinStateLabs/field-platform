"""S11-13: every test this service's README.md and SPEC.md cite exists.

The README named conformance-sentinel `tests/test_d1_metering.py`, which is not on main (the name appeared only in the
Phase F integration commit). A citation to a test that does not exist is evidence that does not exist. Every
`test_*.py` token must resolve to a file, and every `test_*.py::test_name` token to a `def` in that file, somewhere
under the repository's test directories (a bare file name is looked up by base name; a path is taken from the root, or from this service).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[1]
DOCS = [SERVICE / "README.md", SERVICE / "SPEC.md"]
TEST_DIRS = [p for pattern in ("services/*/tests", "packages/*/tests", "tools/tests", "integration/**/tests",
                               "defence-shield/*/tests") for p in REPO.glob(pattern) if p.is_dir()]
FILE_TOKEN = re.compile(r"((?:[\w.\-]+/)*test_\w+\.py)(?:::(test_\w+))?")


def _resolve(token: str) -> list[Path]:
    if "/" in token:   # a path is taken from the repository root, else from this service (`tests/test_x.py`)
        return [p for p in (REPO / token, SERVICE / token) if p.is_file()]
    return [d / token for d in TEST_DIRS if (d / token).is_file()]


def _tokens() -> list[tuple[str, str, str | None]]:
    out = []
    for doc in DOCS:
        if doc.is_file():
            for m in FILE_TOKEN.finditer(doc.read_text(encoding="utf-8")):
                out.append((doc.name, m.group(1), m.group(2)))
    return out


TOKENS = _tokens()


def test_the_scan_sees_the_citations_it_is_meant_to_check():
    names = {t[1].rsplit("/", 1)[-1] for t in TOKENS}
    assert {"test_f1_enforce.py", "test_throttle.py", "test_escalation_atomicity.py"} <= names
    assert any(t[2] for t in TOKENS), "no file::test token was found: the pattern is broken"


@pytest.mark.parametrize("doc,file", sorted({(d, f) for d, f, _ in TOKENS}))
def test_every_cited_test_file_exists(doc, file):
    assert _resolve(file), f"{doc} cites {file}, which is not under any tests directory"


@pytest.mark.parametrize("doc,file,name", sorted({(d, f, n) for d, f, n in TOKENS if n}))
def test_every_cited_test_function_is_defined_in_its_file(doc, file, name):
    paths = _resolve(file)
    assert paths, f"{doc} cites {file}, which does not exist"
    assert any(re.search(rf"^\s*(async\s+)?def {re.escape(name)}\(", p.read_text(encoding="utf-8"), re.M) for p in paths), \
        f"{doc} cites {file}::{name}, which is not defined there"


def test_the_metering_row_cites_the_real_sentinel_tests():
    text = (SERVICE / "README.md").read_text(encoding="utf-8")
    assert "test_d1_metering" not in text
    for name in ("test_one_allow_meters_exactly_one_and_self_stays_zero",
                 "test_log_only_meters_every_shadow_allow_including_steps_1_to_4"):
        assert f"test_throttle_metering.py::{name}" in text
        assert (REPO / "services/conformance-sentinel/tests/test_throttle_metering.py").read_text(
            encoding="utf-8").count(f"def {name}(") == 1
