#!/usr/bin/env python3
"""E-gate for Phase E (the words): every Enforced word cites a test that exists and says it.

Usage: python tools/e_gate.py [--words-only]

Checks (all offline, no estate, no network):
  E1  docs/capstone-evidence/v2-one-liners.md
      - the global estate-status line and the provenance of the "old" column are present
      - twelve systems, numbered 1-12 as in the audit
      - each "old" sentence appears verbatim in v2-one-liners-source.md
      - each Enforced row cites `path::test_name` + a commit; the file exists, the test is
        defined there (AST), an `assert` statement or a `pytest.raises` block in its body
        names the row's "asserts" keyword (a comment, a docstring or a bare string does
        not count), and the commit is an ancestor of HEAD that defines that test at that path
      - each Declared row states a reason
      - README cross-check (the grep): the cited README row is Enforced for an Enforced word
        and Declared for a Declared word; a mismatch in either direction fails
  E2/E3 (unless --words-only): README one-liner column, ROADMAP counts, "RACI-ready" gone,
      PRODUCT/burn-in gone from the three STATE locations
  Words: none of the public files below says certified/compliant-with/guarantees compliance
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
E1 = ROOT / "docs/capstone-evidence/v2-one-liners.md"
SRC = ROOT / "docs/capstone-evidence/v2-one-liners-source.md"
PUBLIC = [E1, ROOT / "README.md", ROOT / "ROADMAP.md"]
BANNED = [
    (re.compile(r"\bcertified\b|\bcertification (?:is|was) (?:achieved|granted)", re.I), "certification claim"),
    (re.compile(r"\bguarantee[sd]? compliance|\bensures? compliance|\bcompliant with\b", re.I), "compliance claim"),
    (re.compile(r"ForceField|Force Field(?! Protocol| Framework)"), "Force-Field spelling"),
]
GLOBAL_LINE = "every Enforced word is test/CI-proven"
NUMBERS = list(range(1, 13))

errors: list[str] = []
ONE: dict[str, str] = {}  # service slug -> one-liner from E1


def fail(msg: str) -> None:
    errors.append(msg)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("`", "").replace("*", "")).strip().lower()


def git(*args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, p.stdout


_ast_cache: dict[str, dict[str, str]] = {}


def functions(path: str) -> dict[str, str]:
    """name -> source of every function defined in the file (nested and in classes)."""
    if path not in _ast_cache:
        text = (ROOT / path).read_text(encoding="utf-8")
        out: dict[str, str] = {}
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(node.name, ast.get_source_segment(text, node) or "")
        _ast_cache[path] = out
    return _ast_cache[path]


def _is_raises(expr: ast.expr) -> bool:
    """`pytest.raises(...)`, `raises(...)` or any `.raises(...)` call."""
    if not isinstance(expr, ast.Call):
        return False
    f = expr.func
    return (isinstance(f, ast.Attribute) and f.attr == "raises") or (isinstance(f, ast.Name) and f.id == "raises")


def _words(node: ast.AST) -> list[str]:
    """Names, attributes and constants inside `node`; a bare string statement (a docstring
    or a string on its own line) is skipped, and comments are not in the AST at all."""
    out: list[str] = []
    stack: list[ast.AST] = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            continue
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.Attribute):
            out.append(n.attr)
        elif isinstance(n, ast.Constant):
            out.append(str(n.value))
        stack.extend(ast.iter_child_nodes(n))
    return out


def assertion_words(body: str) -> tuple[bool, str]:
    """(the test has an assertion, the words its assertions name).

    An assertion is an `assert` statement or a `with pytest.raises(...)` block. The
    words are taken from those nodes only, so a keyword that appears in a comment, a
    docstring, a bare string or the set-up code does not count as "named by the test"
    (reviewer C-493 F-PR308-2: a cited test gutted to `assert True  # keyword` passed).
    """
    try:
        tree = ast.parse(textwrap.dedent(body))
    except SyntaxError:
        return False, ""
    found = False
    words: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            found = True
            words.extend(_words(node))
        elif isinstance(node, ast.With) and any(_is_raises(i.context_expr) for i in node.items):
            found = True
            words.extend(_words(node))
    return found, " ".join(words)


def defines(content: str, name: str) -> bool:
    """`content` defines a function called exactly `name` (not a longer name that starts with it)."""
    return re.search(rf"^\s*(?:async\s+)?def\s+{re.escape(name)}\s*\(", content, re.M) is not None


def readme_rows(slug: str) -> list[tuple[str, str]]:
    """(normalised guarantee cell, status cell) for every table row of the service README."""
    rows = []
    for line in (ROOT / "services" / slug / "README.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.search(r"\*\*(Enforced|Declared)", cells[1]):
            rows.append((norm(cells[0]), cells[1]))
    return rows


def check_citation(where: str, cite: str, sha: str, kw: str) -> None:
    m = re.fullmatch(r"([\w./-]+\.py)::(\w+)", cite)
    if not m:
        return fail(f"{where}: citation is not path::test_name: {cite!r}")
    path, name = m.groups()
    if not (ROOT / path).is_file():
        return fail(f"{where}: {path} does not exist")
    body = functions(path).get(name)
    if body is None:
        return fail(f"{where}: {name} is not defined in {path}")
    if not name.startswith("test_"):
        fail(f"{where}: {name} is not a test function")
    has_assert, named = assertion_words(body)
    if not has_assert:
        fail(f"{where}: {name} contains no assertion")
    elif kw.lower() not in named.lower():
        fail(f"{where}: {name} does not name {kw!r} in an assert or raises block")
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return fail(f"{where}: commit {sha!r} is not a hash")
    rc, _ = git("merge-base", "--is-ancestor", sha, "HEAD")
    if rc != 0:
        return fail(f"{where}: commit {sha} is not an ancestor of HEAD")
    rc, content = git("show", f"{sha}:{path}")
    if rc != 0 or not defines(content, name):
        fail(f"{where}: commit {sha} does not define {name} in {path}")


def check_e1() -> None:
    if not E1.is_file():
        return fail(f"{E1.relative_to(ROOT)} does not exist")
    text = E1.read_text(encoding="utf-8")
    src = norm(SRC.read_text(encoding="utf-8"))
    if GLOBAL_LINE.lower() not in text.lower():
        fail("E1: the global estate-status line is missing")
    if "provenance" not in text.lower() or "v2-one-liners-source.md" not in text:
        fail("E1: the provenance of the old column is not stated")
    parts = re.split(r"^### (\d+) — (.+)$", text, flags=re.M)
    sections = {int(parts[i]): (parts[i + 1], parts[i + 2]) for i in range(1, len(parts) - 2, 3)}
    if sorted(sections) != NUMBERS:
        fail(f"E1: systems numbered {sorted(sections)}, expected 1-12")
    n_enf = n_dec = 0
    for n, (name, body) in sections.items():
        old = re.search(r"\*\*Old \(verbatim\):\*\* (.+)", body)
        new = re.search(r"\*\*New:\*\* (.+)", body)
        why = re.search(r"\*\*Why reworded:\*\* (.+)", body)
        status = re.search(r"\*\*Estate status:\*\* (.+)", body)
        for label, mm in (("Old", old), ("New", new), ("Why reworded", why), ("Estate status", status)):
            if not mm:
                fail(f"E1 {n} {name}: no '{label}' line")
        if old and norm(old.group(1).strip('" ')) not in src:
            fail(f"E1 {n} {name}: the old sentence is not verbatim in v2-one-liners-source.md")
        if status and not status.group(1).startswith("Declared"):
            fail(f"E1 {n} {name}: estate status must be Declared")
        slug = re.search(r"README: `services/([\w-]+)/README.md`", body)
        one = re.search(r"\*\*One-liner:\*\* (.+)", body)
        if not one:
            fail(f"E1 {n} {name}: no 'One-liner' line")
        elif slug:
            ONE[slug.group(1)] = one.group(1).strip()
        rows = readme_rows(slug.group(1)) if slug else []
        if not slug:
            fail(f"E1 {n} {name}: no README line")
        kinds = set()
        for line in body.splitlines():
            if not line.startswith("| Enforced") and not line.startswith("| Declared"):
                continue
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) != 6:
                fail(f"E1 {n} {name}: table row with {len(c)} cells: {line[:70]}")
                continue
            kind, word, cite, sha, kw, prefix = c
            kinds.add(kind)
            where = f"E1 {n} {name} [{word[:48]}]"
            if kind == "Enforced":
                n_enf += 1
                check_citation(where, cite.strip("`"), sha.strip("`"), kw.strip("`"))
            else:
                n_dec += 1
                if len(cite) < 20:
                    fail(f"{where}: a Declared row must state its reason")
            if prefix != "—":
                use = rows
                if prefix.startswith("@"):
                    other, prefix = prefix[1:].split(" ", 1)
                    use = readme_rows(other)
                hit = [st for g, st in use if g.startswith(norm(prefix))]
                if not hit:
                    fail(f"{where}: README row not found: {prefix!r}")
                elif kind == "Enforced" and not all(h.startswith("**Enforced") for h in hit):
                    fail(f"{where}: README row is Declared but E1 says Enforced: {prefix!r}")
                elif kind == "Declared" and not all(h.startswith("**Declared") or re.search(r"Declared (everywhere|until|unless)", h) for h in hit):
                    fail(f"{where}: README row is Enforced but E1 says Declared: {prefix!r}")
        if kinds != {"Enforced", "Declared"}:
            fail(f"E1 {n} {name}: needs at least one Enforced and one Declared row")
    print(f"E1: {len(sections)} systems, {n_enf} Enforced citations, {n_dec} Declared rows checked")


def check_words() -> None:
    for f in PUBLIC:
        if not f.is_file():
            continue
        for ln, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for rx, label in BANNED:
                m = rx.search(line)
                if m and "never" not in line.lower() and "not a " not in line.lower():
                    fail(f"words: {f.name}:{ln} {label}: {m.group(0)!r}")


def check_e2_e3() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not re.search(r"^\| # \| System \|[^\n]*\| One-liner \|", readme, re.M):
        fail("E2: README 12-systems table has no One-liner column")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    for slug, one in ONE.items():
        row = [l for l in readme.splitlines() if l.startswith("|") and f"| {slug} |" in l]
        if not row or one not in row[0]:
            fail(f"E2: README row for {slug} does not carry the E1 one-liner")
        if one not in roadmap:
            fail(f"E2: ROADMAP does not carry the E1 one-liner for {slug}")
    if "209 tests" in roadmap or "collect-only" not in roadmap:
        fail("E2: ROADMAP still carries '209 tests' or does not cite collect-only")
    hits = [str(p.relative_to(ROOT)) for p in (
        ROOT / "services/incident-replay/SPEC.md",
        ROOT / "services/incident-replay/src/incident_replay/cli.py",
        ROOT / "integration/demo/README.md",
        ROOT / "docs/capstone-evidence/phase-3.md",
    ) if "RACI-ready" in p.read_text(encoding="utf-8")]
    if hits:
        fail(f"E2: 'RACI-ready' remains in {hits}")
    for p in (ROOT / "integration/fly/entrypoint.sh", ROOT / "integration/fly/fly.toml"):
        head = "\n".join(p.read_text(encoding="utf-8").splitlines()[:14])
        if re.search(r"PRODUCT|burn-in", head):
            fail(f"E3: {p.relative_to(ROOT)} still says PRODUCT/burn-in")
    state = (ROOT / "STATE.md").read_text(encoding="utf-8", errors="replace")
    cur = state.split("## Current phase", 1)[-1].split("\n## ", 1)[0]
    if "PRODUCT estate" in state or "private burn-in" in state:
        fail("E3: STATE.md still says PRODUCT estate / private burn-in")
    if "Phase E" not in cur:
        fail("E3: STATE.md Current phase does not mention Phase E")


def main() -> int:
    check_e1()
    check_words()
    if "--words-only" not in sys.argv:
        check_e2_e3()
    for e in errors:
        print("FAIL", e)
    print("E-GATE:", "FAIL" if errors else "PASS", f"({len(errors)} problem{'s' if len(errors) != 1 else ''})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
