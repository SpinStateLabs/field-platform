#!/usr/bin/env python3
"""C-1116, C-1122: check and repair the `First read` anchors (`path.py:LINE`) in docs/ENVIRONMENT.md.

The last column of every row names the source line where the variable is first read. A pull request that adds or
removes a line above that read moves the anchor, and the same row then conflicts in every pull request that
touches it (PRs 358, 359, 348, 371, 383 and the rb stacks). This tool ends such a rebase with one command:

    python tools/environment_anchors.py --check   # read-only; exit 1 if any anchor is wrong
    python tools/environment_anchors.py --fix     # rewrites ONLY the line number of a wrong anchor

The first read of a variable is the first line, in the source file the cell names (`<component src dir>/<path>`),
that holds a string constant EXACTLY equal to the variable name, outside docstrings. Comments are not code. A
longer name that contains the variable (`FIELD_X_FILE` for `FIELD_X`), help text and messages that mention it are
not reads. An anchor is right only when it is that line: a docstring, a comment, a longer name and a LATER use of
the same name are all wrong (C-1110, C-1121 F1, F3). `tools/tests/test_environment_doc.py` holds the weaker rule
(the line contains the name); this one is a superset of it.

`--fix` never changes wording, never reorders rows, never touches another column. It moves a wrong anchor to the
first read and prints every move. It does not guess when the file has no such line, when the anchor cell is not
`path.py:LINE` (a leading zero counts as not), when the named file is not unique, or when the variable has two
rows: those are reported and left alone (exit 1). Table-like rows inside a fenced code block are ignored. The doc
is rewritten through a temporary file and a rename. A file that does not parse falls back to whole-name matches on
non-comment lines. Exit codes: 0 all right, 1 wrong or unfixable anchors, 2 usage, 3 the doc cannot be read or
written. Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_REL = "docs/ENVIRONMENT.md"
SOURCE_GLOBS = ("packages/*/src/**/*.py", "services/*/src/**/*.py")
ROW = re.compile(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|(.*)\|\s*$")
ANCHOR = re.compile(r"^(?P<path>[\w./\\-]+\.py):(?P<line>[1-9]\d*)$")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
FENCE = re.compile(r"^\s*(```|~~~)")
FIRST_READ_CELL = 4   # cells after the name: Component, Default, Accepted values, Security impact, First read


def source_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for pattern in SOURCE_GLOBS:
        for p in sorted(root.glob(pattern)):
            files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return files


def read_lines_naming(text: str, name: str) -> list[int]:
    """1-based lines holding a string constant exactly equal to `name`, outside docstrings; the first is the first read."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        whole = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])")
        return [i for i, ln in enumerate(text.splitlines(), 1) if not ln.lstrip().startswith("#") and whole.search(ln)]
    skip = {id(n.value) for n in ast.walk(tree)   # docstrings and other string statements
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
    for n in ast.walk(tree):   # the literal parts of an f-string with a placeholder are pieces of another name
        if isinstance(n, ast.JoinedStr) and any(isinstance(v, ast.FormattedValue) for v in n.values):
            skip.update(id(v) for v in n.values if isinstance(v, ast.Constant))
    return sorted({n.lineno for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and n.value == name and id(n) not in skip})


def parse_rows(doc_text: str) -> list[tuple[int, str, list[str]]]:
    """(index of the line in the file, variable name, cells after the name) for every table row outside a code fence."""
    rows = []
    in_fence = False
    # split on "\n" only (not splitlines): the index must match `apply_fixes`, and a stray U+2028 must not shift it
    for idx, line in enumerate(doc_text.split("\n")):
        line = line.rstrip("\r")
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        m = ROW.match(line)
        if m and not in_fence:
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
        reads = read_lines_naming(text, name)
        if reads and old == reads[0]:
            continue
        if not reads:
            findings.append({"name": name, "kind": "no-read", "old": old, "new": None, "idx": idx,
                             "message": f"{name}: {rel}:{old}; the file has no line reading it; not touched"})
            continue
        first = reads[0]
        if old in reads:
            kind, why = "later-use", f"is a later use; the first read is {first}"
        elif 1 <= old <= len(lines) and name in lines[old - 1]:
            kind, why = "mention", f"only mentions it (docstring, comment, longer name or text); the first read is {first}"
        elif 1 <= old <= len(lines):
            kind, why = "stale", f"does not name it; the first read is {first}"
        else:
            kind, why = "stale", f"is past the end of the file ({len(lines)} lines); the first read is {first}"
        findings.append({"name": name, "kind": kind, "old": old, "new": first, "idx": idx, "rel": rel,
                         "message": f"{name}: {rel}:{old} {why}"})
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


def _read(path: Path) -> str:
    # newline="" keeps the file's own line endings (CRLF or LF) byte for byte
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="read-only; exit 1 if any anchor is wrong")
    mode.add_argument("--fix", action="store_true", help="rewrite the line number of every fixable wrong anchor")
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    args = ap.parse_args(argv)
    doc_path = args.root / DOC_REL
    try:
        doc_text = _read(doc_path)
        sources = source_files(args.root)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"cannot read {doc_path} or the sources: {type(exc).__name__}")
        return 3
    findings = analyse(doc_text, sources)
    for f in findings:
        print(f["message"])
    if args.check:
        print(f"{len(findings)} wrong anchor row(s)")
        return 1 if findings else 0
    fixable = [f for f in findings if f.get("new") is not None]
    if fixable:
        try:
            _write_atomic(doc_path, apply_fixes(doc_text, fixable))
        except OSError as exc:
            print(f"cannot write {doc_path}: {type(exc).__name__}")
            return 3
    remaining = analyse(_read(doc_path), sources)
    print(f"fixed {len(fixable)}; {len(remaining)} left")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
