"""Sessionization, features, the S.* clause pack, verdicts and attribution.

Pure functions over parsed requests. No I/O, no network, no clock: the same
inputs and config always give the same findings (the evidence pack depends
on that).
"""

from __future__ import annotations

import hashlib
import ipaddress
import statistics
from collections import defaultdict
from datetime import datetime

from .models import (
    Campaign,
    ClauseHit,
    Finding,
    Grade,
    LineRef,
    Request,
    RetroConfig,
    SessionFeatures,
    Verdict,
)
from .signatures import (
    hostile_params,
    intermediary_for,
    is_automation_ua,
    markers_for,
    param_values,
)

#: clause refs kept per hit; the detail line says how many were omitted.
MAX_REFS_PER_CLAUSE = 25
#: benign requests kept before the first hostile one, as context.
CONTEXT_BENIGN = 20

SEVERITY_CLAUSES = ("S.inject", "S.debug-probe")
BEHAVIOUR_CLAUSES = ("S.pivot", "S.escalate-on-block")
VERDICT_ORDER = {Verdict.ESCALATE: 0, Verdict.REVIEW: 1, Verdict.AUTHORIZED: 2, Verdict.CLEAR: 3}


class Session:
    def __init__(self, client_ip: str, user_agent: str, requests: list[Request]):
        self.client_ip = client_ip
        self.user_agent = user_agent
        self.requests = requests
        first = requests[0].ts.isoformat()
        digest = hashlib.sha256(f"{client_ip}|{user_agent}|{first}".encode()).hexdigest()
        self.session_id = f"s-{digest[:12]}"


def _order_key(r: Request) -> tuple[datetime, str, int]:
    return (r.ts, r.ref.input, r.ref.line)


def sessionize(requests: list[Request], config: RetroConfig) -> list[Session]:
    groups: dict[tuple[str, str], list[Request]] = defaultdict(list)
    for r in requests:
        groups[(r.client_ip, r.user_agent)].append(r)
    sessions: list[Session] = []
    for (ip, ua), items in groups.items():
        items.sort(key=_order_key)
        current: list[Request] = []
        for r in items:
            if current and (r.ts - current[-1].ts).total_seconds() > config.session_gap_s:
                sessions.append(Session(ip, ua, current))
                current = []
            current.append(r)
        if current:
            sessions.append(Session(ip, ua, current))
    sessions.sort(key=lambda s: (s.requests[0].ts, s.client_ip, s.user_agent))
    return sessions


def features(session: Session) -> SessionFeatures:
    reqs = session.requests
    gaps = [(b.ts - a.ts).total_seconds() for a, b in zip(reqs, reqs[1:])]
    median = statistics.median(gaps) if gaps else None
    cv = None
    if len(gaps) >= 2:
        mean = statistics.fmean(gaps)
        if mean > 0:
            cv = statistics.pstdev(gaps) / mean
    fam: dict[str, int] = defaultdict(int)
    for r in reqs:
        for f in r.families:
            fam[f] += 1
    return SessionFeatures(
        requests=len(reqs),
        duration_s=(reqs[-1].ts - reqs[0].ts).total_seconds(),
        distinct_paths=len({r.path for r in reqs}),
        status_4xx=sum(1 for r in reqs if 400 <= r.status < 500),
        payload_requests=sum(1 for r in reqs if r.is_payload),
        probe_requests=sum(1 for r in reqs if r.is_probe),
        hostile_2xx=sum(1 for r in reqs if r.is_hostile and 200 <= r.status < 300),
        families=dict(sorted(fam.items())),
        interarrival_median_s=median,
        interarrival_cv=cv,
    )


def _hit(clause: str, detail: str, refs: list[LineRef]) -> ClauseHit:
    unique = list(dict.fromkeys(refs))
    extra = len(unique) - MAX_REFS_PER_CLAUSE
    if extra > 0:
        detail = f"{detail} (+{extra} more lines not cited here)"
    return ClauseHit(clause=clause, detail=detail, lines=unique[:MAX_REFS_PER_CLAUSE])


# ------------------------------------------------------------------ clauses


def s_inject(s: Session) -> ClauseHit | None:
    hits = [r for r in s.requests if r.is_payload]
    if not hits:
        return None
    fams = sorted({f for r in hits for f in r.families if f != "debug_probe"})
    return _hit("S.inject", f"{len(hits)} payload request(s); families: {', '.join(fams)}", [r.ref for r in hits])


def s_debug_probe(s: Session) -> ClauseHit | None:
    hits = [r for r in s.requests if r.is_probe]
    if not hits:
        return None
    paths = sorted({r.path for r in hits})[:5]
    return _hit("S.debug-probe", f"{len(hits)} debug/admin/secret probe(s), e.g. {', '.join(paths)}", [r.ref for r in hits])


def s_pivot(s: Session, window_s: float) -> ClauseHit | None:
    """Benign use of path P with parameter k, then the same P and k carrying
    a payload within the window (the A6 'search, then tamper' pattern)."""
    refs: list[LineRef] = []
    pairs = 0
    benign_by_path: dict[str, list[Request]] = defaultdict(list)
    for r in s.requests:
        if not r.is_hostile:
            benign_by_path[r.path].append(r)
            continue
        if not r.is_payload:
            continue
        tampered = hostile_params(r.query)
        if not tampered:
            continue
        r_vals = param_values(r.query)
        for b in reversed(benign_by_path.get(r.path, [])):
            if (r.ts - b.ts).total_seconds() > window_s:
                break
            b_vals = param_values(b.query)
            shared = [k for k in tampered if k in b_vals and b_vals[k] != r_vals.get(k)]
            if shared:
                refs.extend([b.ref, r.ref])
                pairs += 1
                break
    if not pairs:
        return None
    return _hit("S.pivot", f"{pairs} benign→tampered pivot(s) on the same path and parameter within {window_s:.0f} s", refs)


def s_escalate_on_block(s: Session, window_s: float) -> ClauseHit | None:
    """A 4xx answer, then — within the window — a hostile request that either
    follows a BENIGN blocked request or introduces a payload family not seen
    before the block. Plain retries of the same target do not count."""
    refs: list[LineRef] = []
    events = 0
    seen_families: set[str] = set()
    reqs = s.requests
    # next_hostile[i]: index of the first hostile request after i (len = none).
    next_hostile = [len(reqs)] * len(reqs)
    upcoming = len(reqs)
    for i in range(len(reqs) - 1, -1, -1):
        next_hostile[i] = upcoming
        if reqs[i].is_hostile:
            upcoming = i
    for i, blocked in enumerate(reqs):
        if 400 <= blocked.status < 500:
            j = next_hostile[i]
            while j < len(reqs) and (reqs[j].ts - blocked.ts).total_seconds() <= window_s:
                nxt = reqs[j]
                if nxt.path == blocked.path and nxt.query == blocked.query:
                    j = next_hostile[j]  # a plain retry of the same target
                    continue
                new_family = bool(set(nxt.families) - seen_families - set(blocked.families))
                if not blocked.is_hostile or new_family:
                    refs.extend([blocked.ref, nxt.ref])
                    events += 1
                break
        seen_families.update(blocked.families)
    if not events:
        return None
    return _hit("S.escalate-on-block", f"{events} block→escalation step(s) within {window_s:.0f} s", refs)


def s_silent_200(s: Session) -> ClauseHit | None:
    hits = [r for r in s.requests if r.is_hostile and 200 <= r.status < 300]
    if not hits:
        return None
    return _hit(
        "S.silent-200",
        f"{len(hits)} hostile request(s) answered 2xx — no error was raised; check the application for effect",
        [r.ref for r in hits],
    )


def s_cadence(s: Session, feats: SessionFeatures, config: RetroConfig) -> ClauseHit | None:
    if feats.requests < config.cadence_min_requests or feats.interarrival_cv is None:
        return None
    if feats.interarrival_cv >= config.cadence_cv_max:
        return None
    return _hit(
        "S.cadence",
        f"machine-regular timing: {feats.requests} requests, inter-arrival CV {feats.interarrival_cv:.2f} < {config.cadence_cv_max}",
        [s.requests[0].ref, s.requests[-1].ref],
    )


def s_marker(s: Session) -> ClauseHit | None:
    found = markers_for(s.user_agent)
    if not found:
        return None
    return _hit("S.marker", f"self-declared marker(s) in user-agent: {'; '.join(found)} — a claim by the client, spoofable", [s.requests[0].ref])


def s_launder(s: Session) -> ClauseHit | None:
    via = intermediary_for(s.user_agent)
    hostile = [r for r in s.requests if r.is_hostile]
    if not via or not hostile:
        return None
    return _hit(
        "S.launder",
        f"hostile requests arrived through a fetch intermediary ({via}); the client IP is the intermediary's, not the originator's",
        [r.ref for r in hostile],
    )


# ---------------------------------------------------------------- campaigns


def campaigns(sessions: list[Session]) -> list[Campaign]:
    by_fp: dict[str, list[tuple[Session, Request]]] = defaultdict(list)
    for s in sessions:
        for r in s.requests:
            for fp in r.fingerprints:
                by_fp[fp].append((s, r))
    out: list[Campaign] = []
    for fp, items in sorted(by_fp.items()):
        ips = sorted({s.client_ip for s, _ in items})
        if len(ips) < 2:
            continue
        family = fp.split(":", 1)[0]
        out.append(
            Campaign(
                campaign_id=f"c-{hashlib.sha256(fp.encode()).hexdigest()[:10]}",
                fingerprint=fp,
                family=family,
                client_ips=ips,
                session_ids=sorted({s.session_id for s, _ in items}),
                example=items[0][1].ref,
            )
        )
    return out


# ------------------------------------------------------ verdict + attribution


def _allowlisted(s: Session, config: RetroConfig) -> str | None:
    try:
        ip = ipaddress.ip_address(s.client_ip)
    except ValueError:
        ip = None
    for entry in config.allow_ips:
        try:
            if ip is not None and ip in ipaddress.ip_network(entry, strict=False):
                return f"allow_ips {entry}"
        except ValueError:
            if entry == s.client_ip:
                return f"allow_ips {entry}"
    ua = s.user_agent.lower()
    for sub in config.allow_ua_substrings:
        if sub and sub.lower() in ua:
            return f"allow_ua_substrings {sub!r}"
    return None


def verdict_for(clause_ids: set[str]) -> Verdict:
    severe = bool(clause_ids & set(SEVERITY_CLAUSES))
    behaviour = bool(clause_ids & set(BEHAVIOUR_CLAUSES))
    if severe and behaviour:
        return Verdict.ESCALATE
    if severe or "S.launder" in clause_ids:
        return Verdict.REVIEW
    return Verdict.CLEAR


def grade_for(s: Session, clause_ids: set[str]) -> tuple[Grade, str, list[str]]:
    """Attribution grade. Never returns G3: v0.1 verifies no signatures."""
    found = markers_for(s.user_agent)
    via = intermediary_for(s.user_agent)
    suffix = f"; arrived via intermediary ({via}) — the client IP is not the originator" if via else ""
    if found:
        return (
            Grade.G2,
            f"self-declared marker(s) observed: {'; '.join(found)}; spoofable; not proof of operator{suffix}",
            found,
        )
    behaviour = sorted(clause_ids & {"S.pivot", "S.escalate-on-block", "S.cadence"})
    automation = is_automation_ua(s.user_agent)
    if behaviour or automation:
        basis = ", ".join(behaviour + (["automation-library user-agent"] if automation else []))
        return (
            Grade.G1,
            f"behaviour consistent with an automated, goal-seeking client ({basis}); operator unknown{suffix}",
            [],
        )
    return Grade.G0, f"no automation indicator observed{suffix}", []


def _kept_requests(s: Session, hits: list[ClauseHit], include_raw: bool) -> list[Request]:
    cited = {ref for h in hits for ref in h.lines}
    first_hostile = next((i for i, r in enumerate(s.requests) if r.is_hostile), len(s.requests))
    context = {id(r) for r in s.requests[max(0, first_hostile - CONTEXT_BENIGN):first_hostile]}
    kept = [r for r in s.requests if r.is_hostile or r.ref in cited or id(r) in context]
    if not include_raw:
        kept = [r.model_copy(update={"raw": ""}) for r in kept]
    return kept


def evaluate(sessions: list[Session], config: RetroConfig) -> tuple[list[Finding], list[Campaign], dict[str, int]]:
    camps = campaigns(sessions)
    camp_by_session: dict[str, list[Campaign]] = defaultdict(list)
    for c in camps:
        for sid in c.session_ids:
            camp_by_session[sid].append(c)

    findings: list[Finding] = []
    counts = {v.value: 0 for v in Verdict}
    for s in sessions:
        feats = features(s)
        hits = [
            h
            for h in (
                s_inject(s),
                s_debug_probe(s),
                s_pivot(s, config.pivot_window_s),
                s_escalate_on_block(s, config.pivot_window_s),
                s_silent_200(s),
                s_cadence(s, feats, config),
                s_marker(s),
                s_launder(s),
            )
            if h is not None
        ]
        my_camps = camp_by_session.get(s.session_id, [])
        if my_camps:
            fps = {c.fingerprint for c in my_camps}
            refs = [r.ref for r in s.requests if fps & set(r.fingerprints)]
            hits.append(
                _hit(
                    "S.campaign",
                    f"payload fingerprint(s) shared with other client IPs: {', '.join(c.campaign_id for c in my_camps)} — a lead, not an identity",
                    refs,
                )
            )
        ids = {h.clause for h in hits}
        verdict = verdict_for(ids)
        authorized = None
        if verdict is not Verdict.CLEAR:
            authorized = _allowlisted(s, config)
            if authorized:
                verdict = Verdict.AUTHORIZED
        counts[verdict.value] += 1
        if verdict is Verdict.CLEAR:
            continue
        grade, basis, found = grade_for(s, ids)
        findings.append(
            Finding(
                session_id=s.session_id,
                client_ip=s.client_ip,
                user_agent=s.user_agent,
                first_ts=s.requests[0].ts,
                last_ts=s.requests[-1].ts,
                verdict=verdict,
                grade=grade,
                grade_basis=basis,
                markers=found,
                clauses=hits,
                features=feats,
                campaign_ids=[c.campaign_id for c in my_camps],
                authorized_by=authorized,
                requests=_kept_requests(s, hits, config.include_raw),
            )
        )
    findings.sort(key=lambda f: (VERDICT_ORDER[f.verdict], f.first_ts, f.session_id))
    return findings, camps, counts
