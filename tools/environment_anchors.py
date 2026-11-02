#!/usr/bin/env python3
"""C-1116: check and repair the `First read` anchors (`path.py:LINE`) in docs/ENVIRONMENT.md.

The last column of every row names the source line where the variable is read. A pull request that adds or
removes a line above that read moves the anchor, and the same row then conflicts in every pull request that
touches it (PRs 358, 359, 348, 371, 383 and the rb stacks). This tool ends such a rebase with one command:

    python tools/environment_anchors.py --check   # read-only; exit 1 if any anchor is wrong
    python tools/environment_anchors.py --fix     # rewrites ONLY the line number of a wrong anchor

An anchor is right when its line, in the source file it names (`<component src dir>/<path>`), names the
variable in CODE: a docstring or comment line that mentions the name is wrong (C-1110: FORCE_GATEWAY_MOCK cited a
docstring). `tools/tests/test_environment_doc.py` holds the weaker rule (the line contains the name); this one
is a superset of it.

`--fix` never changes wording, never reorders rows, never touches another column. For a wrong anchor it moves
to the code line naming the variable that is nearest to the old number (ties: the lower line); it prints every
move so a person can review it. It does not guess when the file has no code line naming the variable, when the
anchor cell is not `path.py:LINE`, when the named file is not unique, or when the variable has two rows:
those are reported and left alone (exit 1). Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_REL = "docs/ENVIRONMENT.md"
SOURCE_GLOBS = ("packages/*/src/**/*.py", "services/*/src/**/*.py")
ROW = re.compile(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|(.*)\|\s*$")
ANCHOR = re.compile(r"^(?P<path>[\w./\\-]+\.py):(?P<line>\d+)$")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
FIRST_READ_CELL = 4   # cells after the name: Component, Default, Accepted values, Security impact, First read


def source_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for pattern in SOURCE_GLOBS:
        for p in sorted(root.glob(pattern)):
            files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return files


def code_lines_naming(text: str, name: str) -> list[int]:
    """1-based lines where `name` appears in code: inside a string token or as a name, not in a docstring or a comment."""
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [i for i, ln in enumerate(lines, 1) if name in ln]
    doc: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            doc.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    found: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING and name in tok.string:
                found.update(i for i in range(tok.start[0], tok.end[0] + 1) if i not in doc and name in lines[i - 1])
            elif tok.type == tokenize.NAME and tok.string == name and tok.start[0] not in doc:
                found.add(tok.start[0])
    except (tokenize.TokenError, IndentationError):
        return [i for i, ln in enumerate(lines, 1) if name in ln and i not in doc]
    return sorted(found)


def parse_rows(doc_text: str) -> list[tuple[int, str, list[str]]]:
    """(index of the line in the file, variable name, cells after the name) for every table row."""
    rows = []
    # split on "\n" only (not splitlines): the index must match `apply_fixes`, and a stray U+2028 must not shift it
    for idx, line in enumerate(doc_text.split("\n")):
        m = ROW.match(line.rstrip("\r"))
        if m:
            rows.append((idx, m.group(1), [c.strip() for c in UNESCAPED_PIPE.split(m.group(2))]))
    return rows


def _resolve(sources: dict[str, str], rel: str) -> list[str]:
    return [p for p in sources if p.endswith("/src/" + rel.replace("\\", "/"))]


def analyse(doc_text: str, sources: dict[str, str]) -> list[dict]:
    """One finding per wrong row: {name, kind, old, new (or None), message}. An empty list means every anchor is right."""
    rows = parse_rows(doc_text)
    seen: dict[str, int] = {}
    for _, name, _ in rows:
        seen[name] = seen.get(name, 0) + 1
    findings: list[dict] = []
    reported_dupes: set[str] = set()
    for idx, name, cells in rows:
        if seen[name] > 1:
            if name not in reported_dupes:
                reported_dupes.add(name)
                findings.append({"name": name, "kind": "duplicate-row", "old": None, "new": None, "idx": idx,
                                 "message": f"{name}: {seen[name]} rows; not touched"})
            continue
        if len(cells) <= FIRST_READ_CELL:
            findings.append({"name": name, "kind": "short-row", "old": None, "new": None, "idx": idx,
                             "message": f"{name}: no First read cell; not touched"})
            continue
        m = ANCHOR.match(cells[FIRST_READ_CELL])
        if not m:
            findings.append({"name": name, "kind": "unparsed", "old": None, "new": None, "idx": idx,
                             "message": f"{name}: cell {cells[FIRST_READ_CELL]!r} is not path.py:LINE; not touched"})
            continue
        rel, old = m.group("path"), int(m.group("line"))
        files = _resolve(sources, rel)
        if len(files) != 1:
            findings.append({"name": name, "kind": "file", "old": old, "new": None, "idx": idx,
                             "message": f"{name}: {rel!r} matches {len(files)} source files; not touched"})
            continue
        text = sources[files[0]]
        lines = text.splitlines()
        code = code_lines_naming(text, name)
        if old in code:
            continue
        if 1 <= old <= len(lines) and name in lines[old - 1]:
            kind, why = "docstring-or-comment", "names it only in a docstring or comment"
        elif 1 <= old <= len(lines):
            kind, why = "stale", "does not name it"
        else:
            kind, why = "stale", f"is past the end of the file ({len(lines)} lines)"
        if not code:
            findings.append({"name": name, "kind": kind, "old": old, "new": None, "idx": idx,
                             "message": f"{name}: {rel}:{old} {why}; the file has no code line naming it; not touched"})
            continue
        new = min(code, key=lambda c: (abs(c - old), c))
        findings.append({"name": name, "kind": kind, "old": old, "new": new, "idx": idx, "rel": rel,
                         "message": f"{name}: {rel}:{old} {why}; nearest code line naming it is {new}"})
    return findings


def _rewrite_last_cell(line: str, rel: str, old: int, new: int) -> str:
    """Replace `rel:old` with `rel:new` inside the last cell of the row, nothing else."""
    body_end = line.rstrip().rfind("|")
    last_open = max((m.start() for m in UNESCAPED_PIPE.finditer(line[:body_end])), default=-1)
    cell = line[last_open + 1:body_end]
    target = f"{rel}:{old}"
    if cell.count(target) != 1:
        raise ValueError(f"cannot rewrite {target!r} in {cell!r}")
    return line[:last_open + 1] + cell.replace(target, f"{rel}:{new}") + line[body_end:]


def apply_fixes(doc_text: str, findings: list[dict]) -> str:
    lines = doc_text.split("\n")
    for f in findings:
        if f.get("new") is None or f.get("rel") is None:
            continue
        lines[f["idx"]] = _rewrite_last_cell(lines[f["idx"]], f["rel"], f["old"], f["new"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="read-only; exit 1 if any anchor is wrong")
    mode.add_argument("--fix", action="store_true", help="rewrite the line number of every fixable wrong anchor")
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    args = ap.parse_args(argv)
    doc_path = args.root / DOC_REL
    # newline="" keeps the file's own line endings (CRLF or LF) byte for byte
    with open(doc_path, encoding="utf-8", newline="") as fh:
        doc_text = fh.read()
    sources = source_files(args.root)
    findings = analyse(doc_text, sources)
    for f in findings:
        print(f["message"])
    if args.check:
        print(f"{len(findings)} wrong anchor row(s)")
        return 1 if findings else 0
    fixable = [f for f in findings if f.get("new") is not None]
    if fixable:
        with open(doc_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(apply_fixes(doc_text, fixable))
    remaining = [f for f in analyse(open(doc_path, encoding="utf-8", newline="").read(), sources)]
    print(f"fixed {len(fixable)}; {len(remaining)} left")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
