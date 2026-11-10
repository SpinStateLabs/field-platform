"""The synthetic calibration corpus (C-1165). Made up; see README.md: no real traffic, address, host or incident.

Each ``Actor`` is one client (one address, one user agent) with fixed request offsets and a stated expected outcome under
the DEFAULT configuration. Actors that sit on a threshold come in pairs, one step either side of it. ``render()`` turns
the actors into a combined-format log. Deterministic: no clock, no randomness.

Addresses are the RFC 5737 documentation ranges. The user agents and the three test tokens are the ones
``agent_incident_retro.synth`` already carries; the tag letters below only make every hostile target unique, so no two
actors share a payload fingerprint (two clients that do would form a *campaign* and gain ``S.campaign``)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from agent_incident_retro.synth import CHROME, PY, TRAVERSAL, XSS, _clf, _q

T0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
SPACING_S = 7200          # actors start two hours apart; they never share a client, so this is only for reading

BENIGN_SEARCH = "/search?q=divorce+records+1905"


def taut(tag: str) -> str:
    """The synthetic tautology token with a letter, so each use is its own fingerprint."""
    return "' OR '" + tag + "'='" + tag


def sqli(tag: str) -> str:
    return f"/search?q={_q(taut(tag))}"


def lookup(tag: str) -> str:
    return f"/lookup?id={_q(taut(tag))}"


@dataclass(frozen=True)
class Expect:
    verdict: str
    grade: str
    clauses: frozenset[str]


@dataclass(frozen=True)
class Actor:
    name: str
    ip: str
    ua: str
    requests: tuple[tuple[int, str, int], ...]     # (offset in seconds, target, status)
    findings: tuple[Expect, ...]                   # empty: the client is CLEAR (no finding)
    note: str = ""


def _fx(*clauses: str) -> frozenset[str]:
    return frozenset(clauses)


def _regular(first: tuple[int, str, int], gaps: list[int], benign_from: int) -> tuple[tuple[int, str, int], ...]:
    """A hostile first request, then benign pages after each gap (offsets are cumulative)."""
    out = [first]
    t = first[0]
    for i, gap in enumerate(gaps):
        t += gap
        out.append((t, f"/record/{benign_from + i}", 200))
    return tuple(out)


ACTORS: tuple[Actor, ...] = (
    # --- controls: what must stay CLEAR ------------------------------------------------------------------------
    Actor("human-browse", "192.0.2.10", CHROME,
          ((0, "/", 200), (11, "/about", 200), (52, "/collections", 304), (95, "/search?q=census+1911", 200),
           (140, "/record/1043", 404), (203, "/help", 200)),
          (), "irregular timing, no payload"),
    Actor("regular-benign-bot", "192.0.2.11", PY,
          tuple((60 * i, f"/record/{1000 + i}", 200) for i in range(25)),
          (), "perfectly regular timing but nothing hostile: cadence alone is not a verdict"),
    Actor("automation-ua-one-benign", "192.0.2.12", PY,
          ((0, "/about", 200),),
          (), "an automation library user agent alone is not a verdict"),
    # --- a single payload ------------------------------------------------------------------------------------
    Actor("one-shot-payload", "198.51.100.20", CHROME,
          ((0, sqli("a"), 200),),
          (Expect("REVIEW", "G0", _fx("S.inject", "S.silent-200")),), "one payload, no behaviour clause"),
    # --- the pivot window (default 300 s): at it, and one second past it ---------------------------------------
    Actor("pivot-at-window", "203.0.113.30", CHROME,
          ((0, BENIGN_SEARCH, 200), (300, sqli("b"), 200)),
          (Expect("ESCALATE", "G1", _fx("S.inject", "S.pivot", "S.silent-200")),), "tamper exactly 300 s after the benign use"),
    Actor("pivot-past-window", "203.0.113.31", CHROME,
          ((0, BENIGN_SEARCH, 200), (301, sqli("c"), 200)),
          (Expect("REVIEW", "G0", _fx("S.inject", "S.silent-200")),), "the same, 301 s after: outside the window"),
    # --- block then escalate, same window ------------------------------------------------------------------
    Actor("block-escalate-at-window", "203.0.113.32", CHROME,
          ((0, "/search?q=old+records", 404), (300, lookup("d"), 200)),
          (Expect("ESCALATE", "G1", _fx("S.inject", "S.escalate-on-block", "S.silent-200")),),
          "a 404, then a payload on another target 300 s later"),
    Actor("block-escalate-past-window", "203.0.113.33", CHROME,
          ((0, "/search?q=old+records", 404), (301, lookup("e"), 200)),
          (Expect("REVIEW", "G0", _fx("S.inject", "S.silent-200")),), "the same, 301 s later"),
    # --- the session gap (default 1800 s): at it (one session), one second past it (two) --------------------
    Actor("gap-at-limit", "198.51.100.40", CHROME,
          ((0, sqli("f"), 500), (1800, f"/files?name={_q(TRAVERSAL)}", 500)),
          (Expect("REVIEW", "G0", _fx("S.inject")),), "two payloads 1800 s apart are ONE session"),
    Actor("gap-past-limit", "198.51.100.41", CHROME,
          ((0, sqli("g"), 500), (1801, f"/lookup?id={_q(XSS)}", 500)),
          (Expect("REVIEW", "G0", _fx("S.inject")), Expect("REVIEW", "G0", _fx("S.inject"))),
          "two payloads 1801 s apart are TWO sessions"),
    # --- cadence: needs a flagged session; 20 requests and CV below 0.35 ---------------------------------------
    Actor("cadence-at-min-requests", "192.0.2.50", CHROME,
          _regular((0, sqli("h"), 500), [60] * 19, 2000),
          (Expect("REVIEW", "G1", _fx("S.inject", "S.cadence")),), "20 requests, perfectly regular"),
    Actor("cadence-below-min-requests", "192.0.2.51", CHROME,
          _regular((0, sqli("i"), 500), [60] * 18, 3000),
          (Expect("REVIEW", "G0", _fx("S.inject")),), "19 requests, perfectly regular: one short"),
    Actor("cadence-cv-below-limit", "192.0.2.52", CHROME,
          _regular((0, sqli("j"), 500), [33, 67] * 10, 4000),
          (Expect("REVIEW", "G1", _fx("S.inject", "S.cadence")),), "21 requests, gaps 33 and 67 s alternating: CV 0.34"),
    Actor("cadence-cv-at-limit", "192.0.2.54", CHROME,
          _regular((0, sqli("l"), 500), [65, 135] * 10, 6000),
          (Expect("REVIEW", "G0", _fx("S.inject")),),
          "21 requests, gaps 65 and 135 s alternating: CV exactly 0.35, which is NOT below the limit"),
    Actor("cadence-cv-above-limit", "192.0.2.53", CHROME,
          _regular((0, sqli("k"), 500), [32, 68] * 10, 5000),
          (Expect("REVIEW", "G0", _fx("S.inject")),), "21 requests, gaps 32 and 68 s alternating: CV 0.36"),
)


def render() -> str:
    """The combined-format log of every actor, ordered by time, one line per request."""
    rows: list[tuple[datetime, str]] = []
    for index, actor in enumerate(ACTORS):
        start = T0 + timedelta(seconds=SPACING_S * index)
        for offset, target, status in actor.requests:
            ts = start + timedelta(seconds=offset)
            rows.append((ts, _clf(actor.ip, ts, "GET", target, status, 1000 + offset % 997, actor.ua)))
    rows.sort(key=lambda r: (r[0], r[1]))
    return "\n".join(line for _, line in rows) + "\n"
