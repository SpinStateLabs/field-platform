"""S4-5: conformance.py says clause ids are a stable registry ("Add ids; never repurpose one") that services must cite
on every BLOCK / ESCALATE, so every clause-id-shaped literal a service or package emits must be a key of CLAUSES;
otherwise ConformanceVerdict.clause_text() prints '<unknown clause>' for a verdict that was really issued.

The scan walks services/*/src and packages/*/src from the repo root (derived from this file's location), collecting
string literals shaped like a clause id with the AST (docstrings and comments are not literals, so prose never
counts). One id is known to be missing and is named in KNOWN_PENDING. Tests only: the registry is not edited
(adding the id is the owner's ruling)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from field_core.conformance import CLAUSES, ConformanceVerdict, Decision

REPO = Path(__file__).resolve().parents[3]
CLAUSE_ID = re.compile(r"[A-Z]\.[a-z_]+")

#: Emitted but not in CLAUSES, pending a ruling. services/delegation-authority/src/delegation_authority/api.py names
#: MANIFEST_EXPIRED = "D.manifest_expired" PROVISIONAL ("no existing D.* id fits a lapsed or overrun manifest expiry;
#: D.expired is the sentinel's token-status clause. Pending a ruling."). Remove it from this set the day the ruling
#: adds the id to CLAUSES; a stale entry here fails test_the_pending_set_holds_only_ids_that_are_still_missing.
KNOWN_PENDING = {"D.manifest_expired"}


def emitted_clause_ids(root: Path) -> dict[str, list[str]]:
    """{clause-id-shaped literal: [relative path:line, ...]} over services/*/src and packages/*/src under `root`."""
    found: dict[str, list[str]] = {}
    files = [*root.glob("services/*/src/**/*.py"), *root.glob("packages/*/src/**/*.py")]
    for path in sorted(files):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        # the literal pieces of an f-string are fragments, never a whole id
        fragments = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
        for node in ast.walk(tree):
            if id(node) in fragments:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and CLAUSE_ID.fullmatch(node.value):
                found.setdefault(node.value, []).append(f"{path.relative_to(root).as_posix()}:{node.lineno}")
    return found


@pytest.fixture(scope="module")
def emitted():
    if not (REPO / "services").is_dir():
        pytest.skip("not a full repo checkout (no services/ next to packages/)")
    return emitted_clause_ids(REPO)


def test_the_scan_really_finds_the_ids_the_services_emit(emitted):
    # a guard on the scanner itself: if the walk found almost nothing, the main test below would pass for nothing
    assert len(emitted) >= 15, sorted(emitted)
    assert {"E.kill_switch", "D.grantor", "I.manifest", "R.unregistered"} <= set(emitted)


def test_every_emitted_clause_id_is_in_the_registry_or_named_as_pending(emitted):
    unregistered = {cid: where for cid, where in emitted.items() if cid not in CLAUSES and cid not in KNOWN_PENDING}
    assert not unregistered, (
        "clause ids emitted but not in field_core.conformance.CLAUSES (clause_text() would print '<unknown clause>'): "
        + "; ".join(f"{cid} at {', '.join(where[:3])}" for cid, where in sorted(unregistered.items())))


def test_the_pending_set_holds_only_ids_that_are_still_missing(emitted):
    stale = {cid for cid in KNOWN_PENDING if cid in CLAUSES}
    assert not stale, f"now registered, remove from KNOWN_PENDING: {sorted(stale)}"
    gone = {cid for cid in KNOWN_PENDING if cid not in emitted}
    assert not gone, f"no longer emitted anywhere, remove from KNOWN_PENDING: {sorted(gone)}"


def test_an_unregistered_id_prints_as_unknown_in_the_verdict_text():
    # the harm the pending set tolerates, shown with a made-up id so this test is independent of the ruling
    assert "Z.never_registered" not in CLAUSES
    v = ConformanceVerdict(decision=Decision.BLOCK, agent_id="a", action="act", clause_id="Z.never_registered",
                           reasons=["x"])
    assert v.clause_text() == "<unknown clause>"


def test_every_registry_key_has_the_clause_id_grammar():
    bad = [k for k in CLAUSES if not CLAUSE_ID.fullmatch(k)]
    assert not bad, bad
    assert all(isinstance(v, str) and v.strip() for v in CLAUSES.values())


# ---- the scanner flags what it should (a fake id in a temp copy of the tree) -------------------------------------------


def _tree(tmp_path: Path, body: str) -> Path:
    src = tmp_path / "services" / "fake-svc" / "src" / "fake_svc"
    src.mkdir(parents=True)
    (src / "api.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_a_fake_clause_id_literal_is_found_with_its_location(tmp_path):
    root = _tree(tmp_path, 'X = 1\nCLAUSE = "Z.not_registered"\n')
    assert emitted_clause_ids(root) == {"Z.not_registered": ["services/fake-svc/src/fake_svc/api.py:2"]}
    assert "Z.not_registered" not in CLAUSES


def test_prose_and_non_clause_strings_are_not_collected(tmp_path):
    root = _tree(tmp_path, '"""See Z.in_docstring for details."""\n# Z.in_comment\nA = "Z.Mixed_Case"\nB = "z.lower"\n'
                           'C = "Z.has space"\nD = "ZZ.two"\nE = f"Z.fstring_{1}"\n')
    assert emitted_clause_ids(root) == {}


def test_the_same_id_in_two_files_lists_both_places(tmp_path):
    root = _tree(tmp_path, 'A = "E.kill_switch"\n')
    other = tmp_path / "packages" / "p" / "src" / "p"
    other.mkdir(parents=True)
    (other / "m.py").write_text('B = "E.kill_switch"\n', encoding="utf-8")
    assert sorted(emitted_clause_ids(root)["E.kill_switch"]) == ["packages/p/src/p/m.py:1",
                                                                  "services/fake-svc/src/fake_svc/api.py:1"]
