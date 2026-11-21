"""T9: integration/fly/fly.toml [[vm]] is what ``fly deploy -c`` applies, so it must say the size the estate
actually runs (force-field-sandbox: 4 shared CPUs, 2048 MB). A toml that still said ``cpus = 1`` would shrink the
resized machine back at the next deploy. Nothing else in the file is pinned here."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

FLY_TOML = Path(__file__).resolve().parents[2] / "integration" / "fly" / "fly.toml"


def _vm() -> dict:
    vms = tomllib.loads(FLY_TOML.read_text(encoding="utf-8"))["vm"]
    assert len(vms) == 1, "one [[vm]] block: the estate is a single machine"
    return vms[0]


def test_vm_is_four_shared_cpus_and_two_gigabytes():
    vm = _vm()
    assert vm["cpu_kind"] == "shared"
    assert vm["cpus"] == 4
    assert vm["memory"] == "2gb"


# Comment prose must not contradict the parsed ``cpus``. Matches "one/1 (shared) vCPU/CPU", "single vCPU/CPU/core"
# (and "1-CPU"); the T9 resize left "thirteen CPython services cold-starting on one shared vCPU" behind.
_ONE_CPU_CLAIM = re.compile(
    r"\b(?:(?:one|1)[\s-]+(?:shared[\s-]+)?(?:v?cpu|core)s?|single[\s-]+(?:shared[\s-]+)?(?:v?cpu|core))\b",
    re.IGNORECASE,
)


def _comment_lines() -> list[tuple[int, str]]:
    """(1-based line number, comment text) for every ``#`` comment in the file, whole-line or trailing.
    Comment text is joined with the previous line's tail so a claim wrapped across lines is still seen."""
    out = []
    for n, line in enumerate(FLY_TOML.read_text(encoding="utf-8").splitlines(), 1):
        if "#" in line:
            out.append((n, line.split("#", 1)[1].strip()))
    return out


def _wrapped_comment_blocks() -> list[tuple[int, str]]:
    """Consecutive comment lines joined into one string, so "one shared\\n# vCPU" is caught."""
    blocks, cur, start, prev = [], [], 0, -2
    for n, text in _comment_lines():
        if n != prev + 1 and cur:
            blocks.append((start, " ".join(cur)))
            cur = []
        if not cur:
            start = n
        cur.append(text)
        prev = n
    if cur:
        blocks.append((start, " ".join(cur)))
    return blocks


def test_comments_do_not_claim_one_cpu_while_cpus_says_otherwise():
    cpus = _vm()["cpus"]
    stale = [
        (n, m.group(0)) for n, block in _wrapped_comment_blocks() for m in _ONE_CPU_CLAIM.finditer(block) if cpus != 1
    ]
    assert not stale, f"fly.toml comments claim a single CPU but [[vm]] cpus = {cpus}: block starting at line(s) {stale}"


def test_one_cpu_claim_pattern_catches_the_known_phrasings():
    for phrase in ("one shared vCPU", "1 vCPU", "one CPU", "single vCPU", "1-CPU", "one shared vCPU"):
        assert _ONE_CPU_CLAIM.search(f"on {phrase}."), phrase
    assert not _ONE_CPU_CLAIM.search("4 shared CPUs; 1gb was enough for one of the ten services")
