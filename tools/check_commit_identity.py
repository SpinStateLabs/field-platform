#!/usr/bin/env python3
"""Commit-identity guard: no personal mailbox as a commit name or email (C-564, reviewer C-562 F-C562-1).

This repository is public. A commit made on a machine whose git identity was set to a personal address carries that
address as the author NAME and EMAIL for ever (history is not rewritten by a lane). This check reads the author and
committer of every commit in a revision range and reports, per commit, which FIELD is wrong:

``author name`` / ``committer name``    looks like an email address (see "Name rule" below)
``author email`` / ``committer email``  is not an accepted no-reply form (or is empty)

Case: the DOMAIN of an accepted address is matched case-insensitively (email domains are); the rest is as GitHub writes
it (a lower-case ``noreply`` and ``[bot]``; a handle keeps its own case). Anything else is refused.

Accepted email forms: ``<digits>+<handle>@users.noreply.github.com`` and ``<handle>@users.noreply.github.com``
(a handle may hold hyphens and underscores, which Enterprise Managed Users have, and end in ``[bot]``, which GitHub's
bot accounts do),
``noreply@github.com`` (GitHub's own merge identity), ``noreply@anthropic.com`` (the agent no-reply form), and any
address under a domain passed with ``--allow-domain`` (repeatable; the company domain, if wanted: none is built in).

The messages print the commit SHA and the FIELD class, never the value: a failing run must not copy a personal
address into a CI log or a review note. A malformed log line is an error that never echoes the line, and the SHA
column is printed only when it is hex.

Name rule: the name is normalised first (Unicode NFKC, so fullwidth and small-commercial at-signs become ``@``,
no-break spaces become spaces; format characters such as zero-width ones are dropped). It is then flagged when it holds
text, an at-sign and more text; text, spaces and an at-sign before a dotted domain (spaces may also surround the
dots of the domain); a trailing at-sign; a leading
at-sign before a dotted domain; a bracketed ``[at]`` / ``(at)`` / ``{at}`` with no spaces, or with spaces when a dotted
or ``[dot]`` domain follows; or an encoded at-sign (``%40``, ``&#64;``, ``&commat;``) between words. A lone ``@handle``
passes, as do ``look [at] this`` and ``100%40 Club``. Accepted false positives: a name with an at-sign between two
words and no spaces (``C@rl``, ``a@b``, ``J.R@Smith``) is treated as an address, because a machine-derived
``user@host`` name is the common accident; set a normal name. OUT OF SCOPE, by design: spelled-out forms ("at ... dot ..."), homoglyph
letters, and a name that is simply a user name with no at-sign (no rule can tell it from a person). The tool reads
author and committer only, never commit-message trailers (``Co-authored-by``, ``Signed-off-by``), tags or
signatures: an address in a trailer is ACCEPTED by this check (reading bodies needs a multi-line format and a trailer
parser; a lane must not put a personal address in a trailer).

Other limits, stated so nobody relies on more than the tool does:
- an email is matched exactly: padding is a finding (git stores none), the local part of ``noreply`` is case-exact;
- ``--allow-domain D`` accepts EVERY local part under D (the check on an allowed domain is only the domain);
- an empty range is a pass that says ``checked 0 commits``: a wrong or unfetched base that yields an empty range is
  visible only in that count (a base that does not exist is exit 2);
- the CI job checks pull requests only, so a direct push to the default branch, and the commit a squash merge creates
  (its identity depends on the merging account), are NOT checked;
- identities under a GitHub Enterprise Server no-reply host are refused unless that host is passed with
  ``--allow-domain``.

Use (run it from a checkout; it shells out to ``git`` only when it runs):

    python tools/check_commit_identity.py                      # new commits: origin/main..HEAD
    python tools/check_commit_identity.py --range A..B         # an explicit range
    git log --format='%H%x1f%an%x1f%ae%x1f%cn%x1f%ce' A..B | python tools/check_commit_identity.py --stdin

As a pre-push hook (``.git/hooks/pre-push``): ``exec python tools/check_commit_identity.py``. In CI the
``commit-identity`` job of ``.github/workflows/ci.yml`` runs it on pull requests (full-history checkout, range from the
PR base to the PR head, the optional extra domain from the repository variable ``COMMIT_IDENTITY_ALLOW_DOMAIN``).
The default range is the NEW commits only, because the existing history holds older identities that cannot be fixed.

Exit codes: 0 clean, 1 at least one finding, 2 git failed or the input could not be read.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from typing import Iterable, NamedTuple

LOG_FORMAT = "%H%x1f%an%x1f%ae%x1f%cn%x1f%ce"
DEFAULT_RANGE = "origin/main..HEAD"

_HANDLE = r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\[bot\])?"
_NAME_PATTERNS = [
    re.compile(r"[^@\s]+@\S+"),                              # text, an at-sign, more text
    re.compile(r"\w\s*@\s*[\w-]+(?:\s*\.\s*[\w-]+)+"),         # text, spaces around the at-sign, a dotted domain (dots may be spaced)
    re.compile(r"\w@\s*$"),                                  # a trailing at-sign
    re.compile(r"^\s*@[\w-]+\.[\w.-]+"),                      # a leading at-sign before a dotted domain
    re.compile(r"\w[\[({<]at[\])}>]\w", re.IGNORECASE),               # a[at]b (at) {at}, no spaces
    re.compile(r"\w\s*[\[({<]\s*at\s*[\])}>]\s*[\w-]+\s*(?:\.\s*\w|[\[({<]\s*dot\s*[\])}>])", re.IGNORECASE),   # a [at] b.c or a [at] b [dot] c
    re.compile(r"\w(?:%40|&#0*64;|&#x0*40;|&commat;)\w", re.IGNORECASE),   # an encoded at-sign between words
]
_NOREPLY_HOST = r"(?i:users\.noreply\.github\.com)"      # a domain is case-insensitive; the local part is not
NOREPLY_PATTERNS = [
    re.compile(r"[0-9]+\+" + _HANDLE + "@" + _NOREPLY_HOST),
    re.compile(_HANDLE + "@" + _NOREPLY_HOST),
    re.compile(r"noreply@(?i:github\.com)"),
    re.compile(r"noreply@(?i:anthropic\.com)"),
]


class Finding(NamedTuple):
    sha: str
    field: str       # "author name", "author email", "committer name", "committer email"
    reason: str      # "is an email address", "is not an accepted no-reply form", "is empty"

    def __str__(self) -> str:
        return f"{self.sha[:12]}: {self.field} {self.reason}"


def _domain_pattern(domain: str) -> re.Pattern[str]:
    return re.compile(r"[^@\s]+@(?i:" + re.escape(domain.strip().lstrip("@")) + ")")


def email_ok(email: str, allow_domains: Iterable[str] = ()) -> bool:
    patterns = NOREPLY_PATTERNS + [_domain_pattern(d) for d in allow_domains if d.strip()]
    return any(p.fullmatch(email) for p in patterns)


def _normalised(name: str) -> str:
    folded = unicodedata.normalize("NFKC", name)
    folded = "".join(c for c in folded if unicodedata.category(c) != "Cf")
    return folded.strip()


def name_problem(name: str) -> str | None:
    if not name.strip():
        return "is empty"
    view = _normalised(name)
    if not view:
        return "is empty"
    if any(p.search(view) for p in _NAME_PATTERNS):
        return "is an email address"
    return None


def email_problem(email: str, allow_domains: Iterable[str] = ()) -> str | None:
    if not email.strip():
        return "is empty"
    if not email_ok(email, allow_domains):
        return "is not an accepted no-reply form"
    return None


_COMMIT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


def parse_log(text: str) -> list[tuple[str, str, str, str, str]]:
    """Records of ``git log --format=LOG_FORMAT``: (sha, author name, author email, committer name, committer email).

    The errors say what is wrong, never the line: a malformed line may hold an address (a log in the wrong column
    order would put one first)."""
    out = []
    # split on newlines only: str.splitlines() also splits on U+2028, U+0085 and others, which a commit name may hold
    for line in re.split(r"\r?\n", text):
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 5:
            raise ValueError("a log line does not have five fields")
        if not _COMMIT_ID.fullmatch(parts[0]):
            raise ValueError("the first column of a log line is not a commit id")
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
    if not rev_range or rev_range.startswith("-") or any(c in rev_range for c in "\0\n\r"):
        raise ValueError("the range must be a revision range, not an option")
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
    checked = len(parse_log(text))
    if findings:
        print(f"{n} commit(s) carry an identity that must not be public; set user.name and user.email to the "
              "repository identity (a no-reply address) before committing", file=sys.stderr)
        return 1
    print(f"commit identities: clean (checked {checked} commit{'' if checked == 1 else 's'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
