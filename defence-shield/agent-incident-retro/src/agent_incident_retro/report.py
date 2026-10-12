"""Markdown report: summary, per-session timelines, graded attribution, draft notice.

Every attacker-controlled string (paths, queries, user agents) is rendered
inside a code span, so a Markdown viewer shows the payload instead of
executing it.
"""

from __future__ import annotations

from .models import Finding, Grade, Request, RetroResult, Verdict

MAX_TARGET = 110
MAX_TIMELINE_ROWS = 60

# C0/C1 control characters and the unicode line/paragraph separators. Any of
# these in an attacker-controlled string could break out of a table cell or a
# code span and inject Markdown/HTML into the SIGNED report.
_CONTROL = {c: " " for c in list(range(0x00, 0x20)) + list(range(0x7F, 0xA0))}
_CONTROL[0x2028] = " "
_CONTROL[0x2029] = " "
_MD_LEAD = ("#", ">", "-", "+", "*", "=", "|", "`", "~", "!", "[", "]", "(", ")", "_", "<", "&")


def _scrub(text: str) -> str:
    """Collapse every control/separator character to a space. The one place
    attacker bytes are neutralised before they reach Markdown."""
    return " ".join(text.translate(_CONTROL).split()) if text else text


def code(text: str, limit: int = MAX_TARGET) -> str:
    """Render ``text`` inside a code span. Scrubbed first, so no newline or
    control char can escape the span; the renderer escapes HTML inside a span."""
    text = _scrub(text)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    text = text.replace("|", "\\|")
    fence = "``" if "`" in text else "`"
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text or ' '}{pad}{fence}"


def safe(text: str, limit: int = MAX_TARGET) -> str:
    """Inline (non-code) rendering of attacker text: scrub controls, HTML-escape
    ``& < >``, and backslash-escape a leading Markdown block character so the
    string cannot become a heading, list item, blockquote or raw HTML."""
    text = _scrub(text)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|")
    if text[:1] in _MD_LEAD:
        text = "\\" + text
    return text


def phase(r: Request) -> str:
    payload = [f for f in r.families if f != "debug_probe"]
    if payload:
        return "payload: " + ", ".join(payload)
    if r.is_probe:
        return "probe"
    if 400 <= r.status < 500:
        return "blocked"
    return "benign"


def _target(r: Request) -> str:
    return r.path + (f"?{r.query}" if r.query else "")


def _timeline(f: Finding) -> list[str]:
    rows = [
        "| # | Time (UTC) | +s | Method | Target | Status | Phase | Source line |",
        "|---|---|---|---|---|---|---|---|",
    ]
    start = f.requests[0].ts if f.requests else f.first_ts
    shown = f.requests[:MAX_TIMELINE_ROWS]
    for i, r in enumerate(shown, start=1):
        rows.append(
            f"| {i} | {r.ts.strftime('%Y-%m-%d %H:%M:%S')} | {(r.ts - start).total_seconds():.0f} | "
            f"{code(r.method, 10)} | {code(_target(r))} | {r.status} | {phase(r)} | {code(f'{r.ref.input}:{r.ref.line}', 60)} |"
        )
    if len(f.requests) > len(shown):
        rows.append(f"\n_{len(f.requests) - len(shown)} further kept requests are in the evidence pack._")
    return rows


GRADE_TEXT = {
    Grade.G0: "G0: no automation indicator",
    Grade.G1: "G1: behavioural indicators only",
    Grade.G2: "G2: self-declared marker observed (spoofable)",
    Grade.G3: "G3: verified agent identity (not implemented in v0.1)",
}


def _finding(n: int, f: Finding) -> list[str]:
    out = [
        f"### {n}. {f.verdict.value}: session `{f.session_id}`",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Client IP | {code(f.client_ip, 60)} |",
        f"| User-agent | {code(f.user_agent or '(empty)')} |",
        f"| Window (UTC) | {f.first_ts.isoformat()} → {f.last_ts.isoformat()} ({f.features.duration_s:.0f} s) |",
        f"| Requests | {f.features.requests} total; {f.features.payload_requests} payload; {f.features.probe_requests} probe; "
        f"{f.features.status_4xx} answered 4xx; {f.features.hostile_2xx} hostile answered 2xx |",
        f"| Attribution | **{GRADE_TEXT[f.grade]}**: {f.grade_basis} |",
    ]
    if f.campaign_ids:
        out.append(f"| Campaigns | {', '.join(f'`{c}`' for c in f.campaign_ids)} |")
    if f.authorized_by:
        out.append(f"| Authorized | listed, not suppressed: matched {code(f.authorized_by, 80)} |")
    out += ["", "| Clause | Finding | Cited lines |", "|---|---|---|"]
    for h in f.clauses:
        cited = ", ".join(f"{r.input}:{r.line}" for r in h.lines[:6])
        if len(h.lines) > 6:
            cited += f" (+{len(h.lines) - 6})"
        # the detail mixes tool prose with attacker-derived paths — sanitize whole
        out.append(f"| `{h.clause}` | {safe(h.detail, 240)} | {code(cited, 120)} |")
    out += ["", "**Timeline** (hostile requests, cited requests, and up to 20 benign requests before the first hostile one):", ""]
    out += _timeline(f)
    out.append("")
    return out


def _notice(result: RetroResult) -> list[str]:
    notable = [f for f in result.findings if f.verdict in (Verdict.ESCALATE, Verdict.REVIEW)]
    if not notable:
        return []
    window = f"{result.window_first.isoformat()} → {result.window_last.isoformat()}" if result.window_first else "n/a"
    n_esc = sum(f.verdict is Verdict.ESCALATE for f in notable)
    n_rev = sum(f.verdict is Verdict.REVIEW for f in notable)
    lines = [
        "## Draft incident notice (DRAFT: human and legal review required before sending)",
        "",
        "> To: [recipient — verify: your national CERT (in Canada, the Canadian Centre for Cyber Security), "
        "and the abuse contact of any operator named by a self-declared marker]",
        ">",
        f"> We reviewed web logs covering {window} with Agent Incident Retro v{result.tool['version']}, "
        f"an automated triage aid. Its clauses flagged {n_esc} session(s) whose request sequence is **consistent with** "
        f"an automated client that escalated to injection or probing (after a block, or by tampering the same parameter), "
        f"and {n_rev} session(s) with hostile-looking requests but no such sequence. These are clause matches for review, "
        f"not confirmed findings, and not attribution.",
        ">",
    ]
    for f in notable:
        lines.append(
            f"> - `{f.session_id}`: {f.verdict.value}, {safe(f.client_ip, 60)}, {f.first_ts.isoformat()} → {f.last_ts.isoformat()}; "
            f"{GRADE_TEXT[f.grade]} — {safe(f.grade_basis, 240)}."
        )
    lines += [
        ">",
        "> This notice reports observations, not attribution. A user-agent marker is a claim made by the client and can be "
        "forged; behaviour alone cannot distinguish an AI agent from a scripted scanner or an authorized penetration test, "
        "and signature-based clauses can match benign traffic. Treat every line as a lead to verify, not a conclusion. The "
        "signed evidence pack (hash-chained, Ed25519) and our public key are available on request so you can check every "
        "cited log line yourself.",
        "",
    ]
    return lines


def render_markdown(result: RetroResult, generated_at: str) -> str:
    v = result.counts.get("verdicts", {})
    out = [
        "# Agent Incident Retro: evidence report",
        "",
        f"Force-Field-Defence-Shield · {result.tool['name']} v{result.tool['version']} · generated {generated_at} · "
        "**status: DRAFT FOR HUMAN REVIEW**",
        "",
        "**What this report is:** an offline, read-only reading of the logs listed below, with every finding tied to "
        "source lines whose sha-256 digests are sealed in a signed evidence pack.",
        "",
        "**What it is not:** attribution. Grades say what was observed (G1 behaviour, G2 a self-declared marker). "
        "G3 (cryptographically verified agent identity) is not implemented in v0.1. Behaviour alone cannot tell an AI "
        "agent from a scripted scanner or an authorized penetration test.",
        "",
        "## Inputs",
        "",
        "| Input | sha-256 | Lines | Parsed | Unparsed | Format |",
        "|---|---|---|---|---|---|",
    ]
    for i in result.inputs:
        out.append(f"| {code(i.label, 60)} | `{i.sha256}` | {i.lines} | {i.parsed} | {i.unparsed} | {i.format} |")
    window = f"{result.window_first.isoformat()} → {result.window_last.isoformat()}" if result.window_first else "no parsed requests"
    out += [
        "",
        "## Summary",
        "",
        f"- Window: {window}",
        f"- Requests: {result.requests_total}; sessions: {result.sessions_total}",
        f"- Verdicts: ESCALATE {v.get('ESCALATE', 0)} · REVIEW {v.get('REVIEW', 0)} · AUTHORIZED {v.get('AUTHORIZED', 0)} · CLEAR {v.get('CLEAR', 0)}",
        f"- Attribution grades (flagged sessions): {', '.join(f'{k} {n}' for k, n in result.counts.get('grades', {}).items()) or 'none'}",
        f"- Campaigns (same payload from ≥2 client IPs): {len(result.campaigns)}",
        "",
        "## Findings",
        "",
    ]
    if not result.findings:
        out += ["No session met a reporting clause.", ""]
    for n, f in enumerate(result.findings, start=1):
        out += _finding(n, f)
    if result.campaigns:
        out += ["## Campaigns", "", "| Campaign | Family | Client IPs | Sessions | Example line |", "|---|---|---|---|---|"]
        for c in result.campaigns:
            out.append(
                f"| `{c.campaign_id}` | {c.family} | {code(', '.join(c.client_ips), 120)} | {len(c.session_ids)} | "
                f"{code(f'{c.example.input}:{c.example.line}', 60)} |"
            )
        out.append("")
    out += _notice(result)
    out += [
        "## How to verify this report",
        "",
        "```",
        "retro verify evidence-pack.json --pub <signer public key you obtained separately> --report report.md --sources <the log files>",
        "```",
        "",
        "Verification fails unless the hash chain, every event signature, the pack signature, the finding digests, "
        "this report's digest and (with `--sources`) every cited log line all match.",
        "",
    ]
    return "\n".join(out)
