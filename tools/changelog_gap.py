"""List the commits on a branch that CHANGELOG.md does not name (C-591; report only, never a gate).

CHANGELOG.md names a commit by its short id. This reads every 7 to 40 character hex word in the file, finds
the newest commit of ``--ref`` that any of them names, and lists every commit after it, oldest first. It exists
so the file cannot lag silently: the review of 2026-11-03 (reviewer C-539) found 105 commits unentered.

Limits, stated so the output is not read as more than it is:

* a change the CHANGELOG describes WITHOUT naming its commit (older sections cite PR numbers) is invisible
  here; the first line says which commit the comparison starts from;
* a commit is "named" only by an id that is a prefix of its full hash; a hex-looking word that is not a
  commit of the branch is ignored;
* it compares the ids it finds, not whether the entry is true: each claim in the file is still checked
  against the code by a reviewer.

Exit status: 0 always for a report (a gap is printed, not failed); 2 for a usage error, an unreadable file or
a failed ``git log``. Nothing is written.

    python tools/changelog_gap.py [--changelog CHANGELOG.md] [--ref origin/main] [--repo .]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

_ID_RE = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")


def named_ids(text: str) -> set[str]:
    """Every 7 to 40 character lowercase hex word, standing alone, in ``text``."""
    return set(_ID_RE.findall(text))


def commits(repo: str, ref: str) -> list[tuple[str, str]]:
    """(full hash, subject) of every commit reachable from ``ref``, oldest first."""
    proc = subprocess.run(["git", "-C", repo, "log", "--reverse", "--format=%H%x09%s", ref],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError("git log failed for the given repository and ref")
    out = []
    for line in proc.stdout.splitlines():
        sha, _, subject = line.partition("\t")
        if sha:
            out.append((sha, subject))
    return out


def newest_named_index(log: list[tuple[str, str]], ids: set[str]) -> int | None:
    """Index in ``log`` of the newest commit some id in ``ids`` is a prefix of, or None."""
    by_len: dict[int, set[str]] = {}
    for i in ids:
        by_len.setdefault(len(i), set()).add(i)
    newest = None
    for idx, (sha, _) in enumerate(log):
        if any(sha[:n] in group for n, group in by_len.items()):
            newest = idx
    return newest


def report(changelog_text: str, log: list[tuple[str, str]], out: Callable[[str], None] = print) -> int:
    """Print the gap; returns the number of unnamed commits after the newest named one."""
    idx = newest_named_index(log, named_ids(changelog_text))
    if idx is None:
        out("no commit of the branch is named in the changelog: nothing to compare from")
        return 0
    gap = log[idx + 1:]
    out(f"compared from {log[idx][0][:8]} (the newest commit the changelog names): "
        f"{len(gap)} commit(s) after it, of {len(log)} on the branch")
    for sha, subject in gap:
        out(f"{sha[:8]} {subject}")
    return len(gap)


def main(argv: list[str] | None = None, out: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--changelog", default="CHANGELOG.md")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--repo", default=".")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        text = Path(args.changelog).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        print("error: the changelog could not be read", file=sys.stderr)
        return 2
    try:
        log = commits(args.repo, args.ref)
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report(text, log, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
