#!/usr/bin/env python3
"""Commit-identity guard: no personal mailbox as a commit name or email (C-564, reviewer C-562 F-C562-1).

This repository is public. A commit made on a machine whose git identity was set to a personal address carries that
address as the author NAME and EMAIL for ever (history is not rewritten by a lane). This check reads the author and
committer of every commit in a revision range and reports, per commit, which FIELD is wrong:

``author name`` / ``committer name``    looks like an email address (text, an at-sign, then more text, no spaces)
``author email`` / ``committer email``  is not an accepted no-reply form (or is empty)

Accepted email forms: ``<digits>+<handle>@users.noreply.github.com`` and ``<handle>@users.noreply.github.com``,
``noreply@github.com`` (GitHub's own merge identity), ``noreply@anthropic.com`` (the agent no-reply form), and any
address under a domain passed with ``--allow-domain`` (repeatable; the company domain, if wanted: none is built in).

The messages print the commit SHA and the FIELD class, never the value: a failing run must not copy a personal
address into a CI log or a review note.

Use (run it from a checkout; it shells out to ``git`` only when it runs):

    python tools/check_commit_identity.py                      # new commits: origin/main..HEAD
    python tools/check_commit_identity.py --range A..B         # an explicit range
    git log --format='%H%x1f%an%x1f%ae%x1f%cn%x1f%ce' A..B | python tools/check_commit_identity.py --stdin

As a pre-push hook (``.git/hooks/pre-push``): ``exec python tools/check_commit_identity.py``. To run it in CI the
checkout needs the base branch (``fetch-depth: 0``); it is not wired into ``.github/workflows/ci.yml`` by this change.
The default range is the NEW commits only, because the existing history holds older identities that cannot be fixed.

Exit codes: 0 clean, 1 at least one finding, 2 git failed or the input could not be read.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from typing import Iterable, NamedTuple

LOG_FORMAT = "%H%x1f%an%x1f%ae%x1f%cn%x1f%ce"
DEFAULT_RANGE = "origin/main..HEAD"

_EMAIL_AS_NAME = re.compile(r"[^@\s]+@\S+")
NOREPLY_PATTERNS = [
    re.compile(r"[0-9]+\+[A-Za-z0-9][A-Za-z0-9-]*@users\.noreply\.github\.com"),
    re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*@users\.noreply\.github\.com"),
    re.compile(r"noreply@github\.com"),
    re.compile(r"noreply@anthropic\.com"),
]


class Finding(NamedTuple):
    sha: str
    field: str       # "author name", "author email", "committer name", "committer email"
    reason: str      # "is an email address", "is not an accepted no-reply form", "is empty"

    def __str__(self) -> str:
        return f"{self.sha[:12]}: {self.field} {self.reason}"


def _domain_pattern(domain: str) -> re.Pattern[str]:
    return re.compile(r"[^@\s]+@" + re.escape(domain.strip().lstrip("@")))


def email_ok(email: str, allow_domains: Iterable[str] = ()) -> bool:
    patterns = NOREPLY_PATTERNS + [_domain_pattern(d) for d in allow_domains if d.strip()]
    return any(p.fullmatch(email) for p in patterns)


def name_problem(name: str) -> str | None:
    if not name.strip():
        return "is empty"
    if _EMAIL_AS_NAME.search(name):
        return "is an email address"
    return None


def email_problem(email: str, allow_domains: Iterable[str] = ()) -> str | None:
    if not email.strip():
        return "is empty"
    if not email_ok(email.strip(), allow_domains):
        return "is not an accepted no-reply form"
    return None


def parse_log(text: str) -> list[tuple[str, str, str, str, str]]:
    """Records of ``git log --format=LOG_FORMAT``: (sha, author name, author email, committer name, committer email)."""
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 5:
            raise ValueError("a log line does not have five fields")
        out.append((parts[0], parts[1], parts[2], parts[3], parts[4]))
    return out


def check(text: str, allow_domains: Iterable[str] = ()) -> list[Finding]:
    allow = list(allow_domains)
    findings: list[Finding] = []
    for sha, an, ae, cn, ce in parse_log(text):
        for field, value, is_name in (("author name", an, True), ("author email", ae, False),
                                      ("committer name", cn, True), ("committer email", ce, False)):
            reason = name_problem(value) if is_name else email_problem(value, allow)
            if reason:
                findings.append(Finding(sha, field, reason))
    return findings


def _git_log(rev_range: str) -> str:
    proc = subprocess.run(["git", "log", f"--format={LOG_FORMAT}", rev_range], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("git log failed for the range (is the base branch fetched?)")
    return proc.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--range", default=DEFAULT_RANGE, help=f"revision range (default {DEFAULT_RANGE})")
    ap.add_argument("--allow-domain", action="append", default=[], help="accept any address under this domain")
    ap.add_argument("--stdin", action="store_true", help="read `git log --format=...` lines from stdin")
    args = ap.parse_args(argv)
    try:
        text = sys.stdin.read() if args.stdin else _git_log(args.range)
        findings = check(text, args.allow_domain)
    except (RuntimeError, ValueError) as exc:
        print(f"check_commit_identity: {exc}", file=sys.stderr)
        return 2
    for f in findings:
        print(f)
    n = len({f.sha for f in findings})
    if findings:
        print(f"{n} commit(s) carry an identity that must not be public; set user.name and user.email to the "
              "repository identity (a no-reply address) before committing", file=sys.stderr)
        return 1
    print("commit identities: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
