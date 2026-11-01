"""The two SSL agent skills carry no third-party identifiers (C-1088, reviewer C-1076 F-C408-5 on PR 408).

PR 408 (C-758 follow-up) replaced client names, mailboxes and customer codes in these files by placeholders, and
a review found twelve lines of the same classes left over: nothing pinned the result. This guard is structural,
so no real value has to appear here, and it is red on the tree before C-1088:

* no run of five or more digits (a ticket, project or account number; a placeholder names the thing, never the
  number);
* no mailbox outside the project's own domains or the reserved example domains, exactly or as a subdomain (a contact is `<billing contact
  email>`, `<payment mailbox>` or the like);
* every placeholder is a short phrase of words (at most two digits in a row), so a value cannot
  hide inside angle brackets;
* optionally, a deny-list kept OUTSIDE the repository: when ``FIELD_PUBLIC_SAFETY_DENYLIST`` names a readable
  file, none of its non-empty, non-comment lines (a term the owner knows must never appear) is found in either
  skill, case-insensitively. The repository never carries that list; CI runs the structural rules alone.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILLS = (
    ROOT / "agents" / "ssl-timekeeping-agent" / "SKILL.md",
    ROOT / "agents" / "ssl-invoicing-agent" / "SKILL.md",
)
OWN_DOMAINS = ("spinstatelabs.ca", "spinstatelabs.com")
RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
DIGIT_RUN = re.compile(r"\d{5,}")
PORT = re.compile(r"(?<=[>\w]):\d{2,5}(?=[/`\s)'\"]|$)")  # a TCP port after a host or a placeholder is not an identifier
MAILBOX = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PLACEHOLDER = re.compile(r"<([^<>\n]*)>")
PLACEHOLDER_SHAPE = re.compile(r"^(?!.*\d{3})[A-Za-z][A-Za-z0-9 /#'_-]{0,40}$")  # words, no number inside
DENYLIST_ENV = "FIELD_PUBLIC_SAFETY_DENYLIST"


def _allowed_domain(domain: str) -> bool:
    """The project's own domains and the reserved example domains, exactly or as a subdomain: a lookalike with a
    prefix letter glued on (no dot boundary) is not one (Q-60 F-Q60-3)."""
    d = domain.lower().rstrip(".")
    return any(d == a or d.endswith("." + a) for a in OWN_DOMAINS + RESERVED_DOMAINS)


def _lines(path: Path) -> list[tuple[int, str]]:
    return list(enumerate(path.read_text(encoding="utf-8").splitlines(), start=1))


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_no_ticket_project_or_account_number_survives(skill):
    hits = [n for n, line in _lines(skill) if DIGIT_RUN.search(PLACEHOLDER.sub("", PORT.sub("", line)))]  # port first: it follows a placeholder
    assert hits == [], f"{skill.relative_to(ROOT)}: a run of five or more digits on lines {hits} (use a placeholder)"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_no_mailbox_outside_the_own_or_reserved_domains(skill):
    hits = []
    for n, line in _lines(skill):
        for domain in MAILBOX.findall(line):
            if not _allowed_domain(domain):
                hits.append(n)
    assert hits == [], f"{skill.relative_to(ROOT)}: a third-party mailbox on lines {hits} (use a placeholder)"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_every_placeholder_has_the_agreed_shape(skill):
    bad = [(n, inner) for n, line in _lines(skill) for inner in PLACEHOLDER.findall(line)
           if not PLACEHOLDER_SHAPE.match(inner)]
    assert bad == [], f"{skill.relative_to(ROOT)}: placeholders outside the agreed shape: {bad}"


def test_the_skills_carry_no_term_from_the_owners_denylist():
    """Runs the owner's list when it is present; CI has none and relies on the structural rules above."""
    source = os.environ.get(DENYLIST_ENV, "").strip()
    if not source:
        pytest.skip(f"{DENYLIST_ENV} unset: structural rules only")
    terms = [t.strip().lower() for t in Path(source).read_text(encoding="utf-8").splitlines()
             if t.strip() and not t.lstrip().startswith("#")]
    assert terms, "an empty deny-list pins nothing"
    found = []
    for skill in SKILLS:
        text = skill.read_text(encoding="utf-8").lower()
        found += [(skill.parent.name, i) for i, t in enumerate(terms) if t in text]  # the index, never the term
    assert found == [], f"deny-listed terms (by index) found: {found}"


def test_the_denylist_rule_is_live(tmp_path, monkeypatch):
    """The deny-list test itself is pinned: a term that IS in a skill is reported, by index, never by value."""
    word = next(w for w in SKILLS[0].read_text(encoding="utf-8").split() if w.isalpha() and len(w) > 6)
    deny = tmp_path / "deny.txt"
    deny.write_text(f"# owner's list\nno-such-term-{tmp_path.name}\n{word}\n", encoding="utf-8")
    monkeypatch.setenv(DENYLIST_ENV, str(deny))
    with pytest.raises(AssertionError) as e:
        test_the_skills_carry_no_term_from_the_owners_denylist()
    assert word not in str(e.value) and "1)" in str(e.value)


@pytest.mark.parametrize("domain,allowed", [
    ("spinstatelabs.ca", True), ("mail.spinstatelabs.ca", True), ("example.com", True), ("sub.example.org", True),
    ("xspinstatelabs.ca", False), ("notexample.com", False), ("spinstatelabs.ca.evil.test", False),
    ("example.com.attacker.test", False), ("spinstatelabs.co", False),
])
def test_the_domain_check_needs_a_dot_boundary(domain, allowed):
    """F-Q60-3: a lookalike that merely ends with an own or reserved domain is not allowed (made-up hosts only)."""
    assert _allowed_domain(domain) is allowed
