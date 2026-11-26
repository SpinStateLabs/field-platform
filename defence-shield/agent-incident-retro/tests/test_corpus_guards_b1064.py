"""B-1064-GUARDS (roley.reviewer's post-merge review of PR 1064, conditions C1-C3): pins that previously had no test.

1. Regression-only (C1). The synthetic corpora, ``agent_incident_retro.synth_corpus`` and ``tests/corpus_c1165``, are read
   by tests only. No other file in the repository imports or names them, so no threshold, default or CLI path can be
   tuned from or fed by them. This kills reviewer mutants M15, M16, M17 and M23.
2. Synthetic-only content (C2). This repository is public. Every address in either corpus is in an RFC 5737
   documentation range, and the text has no mailbox, URL, host name or secret-shaped token. This kills M19 to M22.
3. Sweep plumbing (C3). ``calibrate.sweep`` replays each grid point with exactly that point's configuration. On these
   corpora the flagged set does not move with the thresholds (test_synth_corpus_s4), so a count-based test cannot see
   the grid being ignored. This test records the configuration that ``run_retro`` receives instead. It kills M11 and M24.
"""
from __future__ import annotations

import ipaddress
import itertools
import os
import re
from pathlib import Path

import pytest

from agent_incident_retro import calibrate
from agent_incident_retro.models import RetroConfig
from agent_incident_retro.synth import generate
from agent_incident_retro.synth_corpus import generate_corpus
from corpus_c1165.corpus import ACTORS, render

PKG_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PKG_ROOT.parents[1]
CORPUS_MODULE = PKG_ROOT / "src" / "agent_incident_retro" / "synth_corpus.py"
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]

# ------------------------------------------------------------------ 1. regression-only

CORPUS_NAMES = re.compile(r"synth_corpus|generate_corpus|corpus_c1165")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "site-packages", ".tox", ".mypy_cache",
             ".pytest_cache", "build", "dist"}


def _is_test_path(rel: Path) -> bool:
    return "tests" in rel.parts or rel.name.startswith("test_") or rel.name == "conftest.py"


def _non_test_sources():
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith((".py", ".sh", ".toml", ".cfg", ".ini", ".yml", ".yaml")):
                path = Path(dirpath) / name
                rel = path.relative_to(REPO_ROOT)
                if not _is_test_path(rel) and path != CORPUS_MODULE:
                    yield path, rel


def test_only_tests_name_the_synthetic_corpora():
    offenders = []
    for path, rel in _non_test_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if CORPUS_NAMES.search(text):
            offenders.append(str(rel))
    assert offenders == [], f"non-test files name a synthetic corpus (regression-only, PR 1064 C1): {offenders}"


def test_the_guard_scans_the_package_sources():
    """A vacuous walk (wrong root, everything skipped) would pass the guard above, so check what it covers."""
    seen = {rel.as_posix() for _, rel in _non_test_sources()}
    base = "defence-shield/agent-incident-retro/src/agent_incident_retro/"
    for module in ("calibrate.py", "cli.py", "engine.py", "models.py", "clauses.py"):
        assert base + module in seen, module
    assert base + "synth_corpus.py" not in seen                # the module itself is the one allowed holder
    assert CORPUS_NAMES.search(CORPUS_MODULE.read_text(encoding="utf-8"))   # and the pattern matches what it defines


@pytest.mark.parametrize("line", ["from .synth_corpus import generate_corpus",
                                  "import agent_incident_retro.synth_corpus as c",
                                  "from corpus_c1165.corpus import ACTORS",
                                  "labels = generate_corpus()[1]"])
def test_the_guard_pattern_catches_each_import_shape(line):
    assert CORPUS_NAMES.search(line)


# ------------------------------------------------------------------ 2. synthetic-only content

DOTTED_QUAD = re.compile(r"(?<![\w./])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")   # not a version such as Chrome/126.0.0.0
MAILBOX = re.compile(r"[\w.+-]+@[\w-]+")
HOSTNAME = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|dev|app|co|uk|de|gov|edu|internal|local|"
                      r"cloud|ai|sh|xyz|info|biz)\b", re.IGNORECASE)
SECRETS = {
    "aws key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "stripe key": re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{8,}"),
    "github token": re.compile(r"\b(?:gh[pousr]_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,})"),
    "slack token": re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "jwt": re.compile(r"\beyJ[0-9A-Za-z_-]{8,}\.[0-9A-Za-z_-]{8,}"),
    "google api key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "long opaque token": re.compile(r"(?<![0-9A-Za-z])[0-9A-Za-z+/_-]{40,}(?![0-9A-Za-z])"),
}


def _corpora():
    for seed in (11, 0, 12345):
        text, labels = generate_corpus(seed=seed)
        yield f"synth_corpus seed {seed}", text, set(labels)
    yield "corpus_c1165", render(), {a.ip for a in ACTORS}


CORPORA = list(_corpora())


def _in_doc_range(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return any(ip in net for net in DOC_NETS)


@pytest.mark.parametrize("name, text, labelled", CORPORA, ids=[c[0] for c in CORPORA])
def test_every_address_in_the_corpus_is_a_documentation_address(name, text, labelled):
    clients = {line.split(" ", 1)[0] for line in text.splitlines() if line}
    assert clients and clients == labelled, name
    off = sorted(a for a in clients | labelled if not _in_doc_range(a))
    off += sorted(q for q in set(DOTTED_QUAD.findall(text)) if not _in_doc_range(q))
    assert off == [], (name, off[:5])


@pytest.mark.parametrize("name, text, labelled", CORPORA, ids=[c[0] for c in CORPORA])
def test_the_corpus_holds_no_mailbox_host_or_secret(name, text, labelled):
    assert not MAILBOX.search(text), (name, "mailbox")
    assert "://" not in text, (name, "url")
    assert not HOSTNAME.search(text), (name, HOSTNAME.search(text).group(0) if HOSTNAME.search(text) else "")
    hits = {kind: rx.search(text).group(0)[:12] for kind, rx in SECRETS.items() if rx.search(text)}
    assert hits == {}, (name, hits)


def _quad(*octets: int) -> str:
    """A non-documentation address built at run time, so the repository's public-safety guard sees no literal."""
    return ".".join(map(str, octets))


@pytest.mark.parametrize("planted", [
    "203.0.113.5 ua bob@example.org", _quad(10, 0, 0, 7), "198.51.100.9 AKIAABCDEFGHIJKLMNOP", _quad(172, 16, 4, 2),
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0", "https://intranet.corp.internal/x", "ghp_" + "a1" * 18,
    "-----BEGIN RSA PRIVATE KEY-----", "api.example.com",
])
def test_the_content_checks_catch_each_planted_value(planted):
    """Each planted value fails at least one of the checks above."""
    bad_quads = [q for q in DOTTED_QUAD.findall(planted) if not _in_doc_range(q)]
    caught = (bool(bad_quads) or bool(MAILBOX.search(planted)) or "://" in planted or bool(HOSTNAME.search(planted))
              or any(rx.search(planted) for rx in SECRETS.values()))
    assert caught, planted


def test_a_browser_version_is_not_read_as_an_address():
    assert DOTTED_QUAD.findall("Chrome/126.0.0.0 Safari/537.36") == []
    assert DOTTED_QUAD.findall("203.0.113.5 - - [01/Sep/2026") == ["203.0.113.5"]


# ------------------------------------------------------------------ 3. the sweep replays each grid point's config

GRID = {"pivot_window_s": [60.0, 900.0], "session_gap_s": [600.0, 3600.0],
        "cadence_min_requests": [10, 40], "cadence_cv_max": [0.2, 0.5]}


def test_the_sweep_runs_each_grid_point_with_exactly_that_config(tmp_path, monkeypatch):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    seen: list[RetroConfig] = []
    real = calibrate.run_retro

    def spy(paths, fmt="clf", config=None, **kw):
        seen.append(config)
        return real(paths, fmt=fmt, config=config, **kw)

    monkeypatch.setattr(calibrate, "run_retro", spy)
    points = calibrate.sweep([log], {"192.0.2.100": "benign"}, GRID)

    keys = list(GRID)
    want = [dict(zip(keys, values)) for values in itertools.product(*(GRID[k] for k in keys))]
    assert len(points) == len(seen) == len(want) == 16
    for point, config, cfg in zip(points, seen, want):
        assert point.config == cfg
        assert isinstance(config, RetroConfig)
        assert {k: getattr(config, k) for k in keys} == cfg, (cfg, config)
    # no two runs share a configuration, and none of them is the default configuration in disguise
    assert len({tuple(getattr(c, k) for k in keys) for c in seen}) == 16
