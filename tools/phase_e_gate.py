"""Phase E gate: every Enforced word in docs/capstone-evidence/v2-one-liners.md is backed by a real test.

For each Enforced row `| word | `path::test_name` | `commit` | `needle` |` it checks that

1. the file exists and defines `test_name` (a function, or a method of a class);
2. the needle is a literal substring of that test's source (the test asserts the word's subject);
3. the commit exists (skipped with --no-commits, for shallow clones);

and then greps every service README: a row whose status is "Declared only" may not contain an
Enforced word of the same system's one-liner (case-insensitive phrase match), and a word may not
be listed both Enforced and Declared in the one-liners file.

Exit 0 = all checks pass, 1 = at least one failure, 2 = the file could not be read.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "capstone-evidence" / "v2-one-liners.md"
CELL = re.compile(r"(?<!\\)\|")
HEADING = re.compile(r"^## (\d+) — (.+)$")
README_OF = {
    1: "agent-registry", 2: "conformance-sentinel", 3: "delegation-authority", 4: "kill-switch",
    5: "sealed-ledger", 6: "incident-replay", 7: "compliance-crosswalk", 8: "federation-broker",
    9: "spend-governor", 10: "force-gateway", 11: "lifecycle-manager", 12: "attestation-reporter",
}


def parse(text: str):
    """Yield (system_number, enforced_rows, declared_words); a row is (word, cite, commit, needle)."""
    systems: dict[int, dict] = {}
    cur = None
    in_declared = False
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            cur = int(m.group(1))
            systems[cur] = {"enforced": [], "declared": []}
            in_declared = False
            continue
        if cur is None:
            continue
        if line.startswith("Declared:"):
            in_declared = True
        elif line.startswith("Reworded:"):
            in_declared = False
        if in_declared and line.startswith("- **"):
            systems[cur]["declared"].append(line[4:].split("**", 1)[0])
        elif line.startswith("| ") and "::" in line:
            cells = [c.strip() for c in CELL.split(line.strip().strip("|"))]
            if len(cells) == 4:
                word, cite, commit, needle = (cells[0], *(c.strip("`") for c in cells[1:]))
                systems[cur]["enforced"].append((word.replace("\\|", "|"), cite, commit, needle.replace("\\|", "|")))
    return systems


def test_source(path: Path, name: str) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    src = path.read_text(encoding="utf-8").splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(src[node.lineno - 1:node.end_lineno])
    return None


def commit_exists(sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=ROOT,
                          capture_output=True).returncode == 0


def declared_only_rows(readme: Path):
    for n, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("|") and re.search(r"\|\s*\*\*Declared only\*\*\s*\|", line):
            yield n, line


def run(doc: Path, check_commits: bool) -> list[str]:
    fails: list[str] = []
    systems = parse(doc.read_text(encoding="utf-8"))
    if sorted(systems) != list(range(1, 13)):
        fails.append(f"expected systems 1-12, found {sorted(systems)}")
    for n, s in sorted(systems.items()):
        if not s["enforced"]:
            fails.append(f"system {n}: no Enforced rows")
        for word, cite, commit, needle in s["enforced"]:
            path_s, _, name = cite.partition("::")
            path = ROOT / path_s
            if not path.is_file():
                fails.append(f"system {n} '{word}': {path_s} does not exist")
                continue
            body = test_source(path, name)
            if body is None:
                fails.append(f"system {n} '{word}': {cite} not found")
            elif needle not in body:
                fails.append(f"system {n} '{word}': needle {needle!r} not in the body of {cite}")
            if check_commits and not commit_exists(commit):
                fails.append(f"system {n} '{word}': commit {commit} not found")
        enforced_words = [w.lower() for w, *_ in s["enforced"]]
        for d in s["declared"]:
            if d.lower() in enforced_words:
                fails.append(f"system {n}: '{d}' is listed both Enforced and Declared")
        readme = ROOT / "services" / README_OF[n] / "README.md"
        if readme.is_file():
            for ln, line in declared_only_rows(readme):
                low = line.lower()
                for w in enforced_words:
                    if len(w) >= 12 and w in low:
                        fails.append(f"{readme.relative_to(ROOT)}:{ln} 'Declared only' row contains Enforced word '{w}'")
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--doc", type=Path, default=DOC)
    ap.add_argument("--no-commits", action="store_true", help="skip the git commit-exists check")
    a = ap.parse_args(argv)
    try:
        fails = run(a.doc, not a.no_commits)
    except OSError as e:
        print(f"phase_e_gate: cannot read {a.doc}: {e}", file=sys.stderr)
        return 2
    systems = parse(a.doc.read_text(encoding="utf-8"))
    rows = sum(len(s["enforced"]) for s in systems.values())
    for f in fails:
        print("FAIL", f)
    print(f"phase_e_gate: {len(systems)} systems, {rows} Enforced rows, {len(fails)} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
