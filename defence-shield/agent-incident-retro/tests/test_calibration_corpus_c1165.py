"""C-1165: the retro over the SYNTHETIC calibration corpus (tests/corpus_c1165; README there).

1. Every labelled actor gets its stated verdict, grade and clause set under the DEFAULT configuration.
2. Each default threshold is pinned by a pair of actors one step either side of it; moving that one threshold by one
   step flips exactly the actor that sits on it (the sweep tests).
3. The corpus itself is synthetic and deterministic (documentation addresses only, a unique payload per actor, the
   README says so)."""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path

import pytest

from agent_incident_retro.engine import run_retro
from agent_incident_retro.models import RetroConfig
from corpus_c1165.corpus import ACTORS, render

README = Path(__file__).resolve().parent / "corpus_c1165" / "README.md"
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
BY_NAME = {a.name: a for a in ACTORS}


def _run(tmp_path: Path, **config):
    log = tmp_path / "corpus.log"
    log.write_text(render(), encoding="utf-8")
    return run_retro([log], fmt="clf", config=RetroConfig(**config) if config else None)


def _findings(result, name: str):
    ip = BY_NAME[name].ip
    return sorted((f for f in result.findings if f.client_ip == ip), key=lambda f: f.first_ts)


def _clauses(finding) -> set[str]:
    return {c.clause for c in finding.clauses}


@pytest.fixture()
def default(tmp_path):
    return _run(tmp_path)


# --- 1. the labels, under the defaults ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [a.name for a in ACTORS])
def test_each_actor_gets_its_label_under_the_defaults(default, name):
    actor, found = BY_NAME[name], _findings(default, name)
    assert len(found) == len(actor.findings), (name, [(f.verdict.value, sorted(_clauses(f))) for f in found])
    for finding, want in zip(found, actor.findings):
        assert (finding.verdict.value, finding.grade.value, _clauses(finding)) == (want.verdict, want.grade, set(want.clauses)), name


def test_the_corpus_parses_completely_and_has_no_campaign(default):
    assert default.inputs[0].unparsed == 0 and default.inputs[0].parsed == default.requests_total
    assert default.campaigns == [], "every actor has its own payload; a campaign means two actors share one"


def test_the_at_limit_actor_sits_exactly_on_the_default_limit(default):
    (finding,) = _findings(default, "cadence-cv-at-limit")
    assert finding.features.interarrival_cv == RetroConfig().cadence_cv_max     # 0.35, not 0.3499 or 0.3501


def test_the_verdict_counts_add_up(default):
    verdicts = default.counts["verdicts"]
    flagged = sum(len(a.findings) for a in ACTORS)
    assert verdicts["CLEAR"] + flagged == default.sessions_total
    escalating = sum(1 for a in ACTORS for f in a.findings if f.verdict == "ESCALATE")      # pivot and block, at the window
    assert escalating == 2
    assert verdicts["ESCALATE"] == 2 and verdicts["REVIEW"] == flagged - 2 and verdicts["AUTHORIZED"] == 0


# --- 2. one threshold, one step: exactly the actor on it flips ---------------------------------------------------

def _verdict_and_clauses(result, name):
    return [(f.verdict.value, frozenset(_clauses(f))) for f in _findings(result, name)]


@pytest.mark.parametrize("config, name, clause, present_after", [
    ({"pivot_window_s": 299.0}, "pivot-at-window", "S.pivot", False),                # 300 s is no longer inside
    ({"pivot_window_s": 301.0}, "pivot-past-window", "S.pivot", True),               # 301 s now is
    ({"pivot_window_s": 299.0}, "block-escalate-at-window", "S.escalate-on-block", False),
    ({"pivot_window_s": 301.0}, "block-escalate-past-window", "S.escalate-on-block", True),
    ({"cadence_min_requests": 21}, "cadence-at-min-requests", "S.cadence", False),   # 20 requests are now one short
    ({"cadence_min_requests": 19}, "cadence-below-min-requests", "S.cadence", True),
    ({"cadence_cv_max": 0.33}, "cadence-cv-below-limit", "S.cadence", False),        # CV 0.34 is no longer below it
    ({"cadence_cv_max": 0.37}, "cadence-cv-above-limit", "S.cadence", True),         # CV 0.36 now is
    ({"cadence_cv_max": 0.36}, "cadence-cv-at-limit", "S.cadence", True),            # CV exactly 0.35 is below 0.36
])
def test_moving_one_threshold_one_step_flips_the_actor_on_it(tmp_path, default, config, name, clause, present_after):
    before = _findings(default, name)
    after = _findings(_run(tmp_path, **config), name)
    assert all((clause in _clauses(f)) is (not present_after) for f in before), (config, name)
    assert all((clause in _clauses(f)) is present_after for f in after), (config, name)


@pytest.mark.parametrize("config", [
    {"pivot_window_s": 299.0}, {"pivot_window_s": 301.0}, {"cadence_min_requests": 21}, {"cadence_min_requests": 19},
    {"cadence_cv_max": 0.33}, {"cadence_cv_max": 0.37}, {"session_gap_s": 1799.0}, {"session_gap_s": 1801.0},
])
def test_one_step_moves_only_the_actors_on_that_threshold(tmp_path, default, config):
    """No other actor changes: the pairs are the only thing sitting on a threshold."""
    after = _run(tmp_path, **config)
    changed = {a.name for a in ACTORS if _verdict_and_clauses(default, a.name) != _verdict_and_clauses(after, a.name)
               or len(_findings(default, a.name)) != len(_findings(after, a.name))}
    on_threshold = {
        "pivot_window_s": {"pivot-at-window", "pivot-past-window", "block-escalate-at-window", "block-escalate-past-window"},
        "cadence_min_requests": {"cadence-at-min-requests", "cadence-below-min-requests"},
        "cadence_cv_max": {"cadence-cv-below-limit", "cadence-cv-at-limit", "cadence-cv-above-limit"},
        "session_gap_s": {"gap-at-limit", "gap-past-limit"},
    }[next(iter(config))]
    assert changed and changed <= on_threshold, (config, sorted(changed))


@pytest.mark.parametrize("config, name, findings", [
    ({"session_gap_s": 1799.0}, "gap-at-limit", 2),        # 1800 s now splits the session
    ({"session_gap_s": 1801.0}, "gap-past-limit", 1),      # 1801 s now joins it
])
def test_the_session_gap_splits_and_joins_exactly_at_the_limit(tmp_path, config, name, findings):
    assert len(_findings(_run(tmp_path, **config), name)) == findings


# --- 3. the corpus is synthetic and deterministic ------------------------------------------------------------------

def test_every_address_is_in_a_documentation_range():
    for actor in ACTORS:
        ip = ipaddress.ip_address(actor.ip)
        assert any(ip in net for net in DOC_NETS), actor.name
    log_ips = {line.split(" ", 1)[0] for line in render().splitlines()}
    assert log_ips == {a.ip for a in ACTORS}


def test_every_actor_has_its_own_address_and_its_own_name():
    # a shared payload would show up as a campaign (asserted above); a shared address would merge two actors' sessions
    assert len({a.ip for a in ACTORS}) == len(ACTORS) and len({a.name for a in ACTORS}) == len(ACTORS)


def test_render_is_deterministic():
    assert render() == render()


def test_the_readme_says_it_is_synthetic_and_not_a_real_calibration():
    text = README.read_text(encoding="utf-8")
    assert re.search(r"\*\*Everything in this directory is made up\.\*\*", text)
    assert "not real calibration" in text.lower() and "RFC 5737" in text


def test_the_corpus_names_no_host_and_no_mailbox():
    log = render()
    assert "@" not in log                                  # an at sign would be a mailbox
    assert not re.search(r"https?://", log)                # and a URL would name a host
