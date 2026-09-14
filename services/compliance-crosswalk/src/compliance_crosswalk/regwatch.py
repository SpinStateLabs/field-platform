"""Regulatory source watch — content-change detection over the cited sources.

GOVERNANCE RATIONALE (ADR 07 §3/§4, v1.2 D4): the crosswalk's citations were
verified against named pages on one retrieval date. regwatch re-reads those
pages and compares a hash of their NORMALISED TEXT with the last reading.
A difference flags the framework stale (``StaleStore.apply_mark``), which
hard-blocks evidence packs until a NAMED human re-review clears it — and that
clear exists only on the CLI, never as an HTTP route.

What this is, and what it is not:

- **Content change, not semantics.** A flag says "the text of a cited page
  moved since the last reading". It never says the change is material, and
  it cannot tell an amendment from a re-worded footer. A human decides.
- **Normalised text, not raw bytes.** Live pages carry per-response nonces,
  CSRF tokens and banners in markup. The hash target strips script/style
  content, comments and tags (``<meta>`` carries no text, so it is dropped
  with them), unescapes entities and collapses whitespace. ``byte_diff`` is
  still reported on the raw bytes.
- **First reading = baseline.** A URL never read before stores its hash and
  flags nothing (status ``baseline``).
- **Unreachable is never changed.** A fetch that fails leaves the stored
  hash untouched, flags nothing and is reported ``unreachable``.
- **A reading must be anchored.** A 200 counts as a reading of a URL only
  if its normalised text names at least ONE of the reference identifiers
  cited from that URL ("Article 12", "Principle 2.1", "GOVERN 1.6" …,
  derived from ``CONTROLS``). A bot-challenge page, soft 404 or moved page
  names none: ``unreachable`` (``anchor missing``), never ``changed``.
- **ISO/IEC 42001 is never fetched.** Every ISO entry is pending-purchase:
  there is no cited page, so the row is ``no-source`` with zero fetches.
- **A manual reading is a named human's file.** ``check_file`` (CLI
  ``regwatch check-file``) takes a page a named human saved from a browser
  (OSFI answers 403 to the honest User-Agent) through the same
  normalisation, anchor rule, compare and flag, recorded as
  ``via: manual:<NAME>`` with the file's sha256. It proves only what that
  human saved — not that the bytes came from the cited URL.

Source inventory is DERIVED from ``mapping.CONTROLS`` (the distinct
``source_url`` of each framework's cited entries), never typed twice. The EU
AI Act was verified via mirror pages, so it gets an ordered candidate list:
the official EUR-Lex ELI rendering first, then the mirror pages. When the
official URL answers, it is the reading (``fetched_via: official``); when it
does not (403, timeout …) the mirrors are read and the fallback is reported
(``fetched_via: mirror`` plus ``fallbacks``). ``Citation.source_url`` is not
touched — it records what was read on RETRIEVED.

Egress discipline of the default fetcher: ``httpx`` with a 20 s timeout,
redirects followed but https only (every hop is checked before it is sent),
an 8 MB cap, and a User-Agent header — no ``x-field-auth`` or any other
platform credential ever goes to a third-party host.

Exit semantics (CLI): 0 = no NEW change detected and every needed source
read; 3 = a change was detected on this run (a flag was set or re-set); 2 =
no new change, but at least one needed source could not be read. A flag that
was already standing does not change the exit code — it shows as
``flag_active`` per framework, and the CLI names it on stderr.
``check-file``: 0 = baseline or unchanged, 3 = the file differs and set a
flag, 2 = refused (not HTML / empty / over the cap / not a reading / bad
arguments) with nothing written.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

import httpx

from compliance_crosswalk import __version__
from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, SRC_EU_OFFICIAL
from compliance_crosswalk.staleness import StaleStore

log = logging.getLogger("compliance_crosswalk.regwatch")

USER_AGENT = f"field-platform-crosswalk/{__version__}"
TIMEOUT_SECONDS = 20
MAX_BYTES = 8 * 1024 * 1024

EXIT_UNCHANGED = 0
EXIT_UNREACHABLE = 2
EXIT_CHANGED = 3

# Frameworks whose cited pages are NOT the official text: the official
# rendering is tried first, the cited pages become the ``mirror`` tier.
OFFICIAL_CANDIDATES: dict[str, str] = {"eu-ai-act": SRC_EU_OFFICIAL}

Fetcher = Callable[[str], bytes]


class FetchError(Exception):
    """A source could not be read (non-200, off-https, over the cap …)."""


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class WatchEntry:
    framework: str
    # Ordered ``(via, url)`` candidates; consecutive entries with the same
    # ``via`` form one tier. Empty ⇒ no-source.
    candidates: tuple[tuple[str, str], ...]
    no_source_reason: str | None = None
    # ``(url, anchors)``: the cited reference identifiers ("Article 12",
    # "Principle 2.1", "GOVERN 1.6") a reading of that URL must contain.
    anchors: tuple[tuple[str, tuple[str, ...]], ...] = ()


# The identifier a cited reference starts with: a word and a (dotted) number.
_REFERENCE_ID = re.compile(r"^\s*([A-Za-z]+\s+\d+(?:\.\d+)*)")


def anchor_of(reference: str | None) -> str | None:
    """``"Article 14 (Human Oversight) ¶1 — …"`` → ``"Article 14"``;
    ``"Principle 1.2 / §B.2 — …"`` → ``"Principle 1.2"``; None if the
    reference does not start with an identifier."""
    match = _REFERENCE_ID.match(reference or "")
    return " ".join(match.group(1).split()) if match else None


def has_anchor(text: str, anchors: tuple[str, ...]) -> bool:
    """True when the normalised text contains ANY anchor as a whole token
    (case-insensitive; "Principle 1.10" does not satisfy "Principle 1.1")."""
    for anchor in anchors:
        pattern = r"(?<!\w)" + r"\s+".join(map(re.escape, anchor.split())) + r"(?!\w)"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def inventory() -> dict[str, WatchEntry]:
    """Watched sources per framework, derived from ``CONTROLS``."""
    out: dict[str, WatchEntry] = {}
    for framework in FRAMEWORKS:
        citations = [c.citations[framework] for c in CONTROLS]
        cited = sorted({c.source_url for c in citations
                        if c.status == "cited" and c.source_url})
        if not cited:
            reason = "/".join(sorted({c.status for c in citations})) or "no entries"
            out[framework] = WatchEntry(framework, (), reason)
            continue
        by_url: dict[str, set[str]] = {url: set() for url in cited}
        for c in citations:
            anchor = anchor_of(c.reference) if c.status == "cited" else None
            if anchor and c.source_url:
                by_url[c.source_url].add(anchor)
        anchors = tuple((url, tuple(sorted(by_url[url]))) for url in cited)
        official = OFFICIAL_CANDIDATES.get(framework)
        if official:
            candidates = (("official", official),) + tuple(("mirror", u) for u in cited)
            # the official text carries every article the mirror pages carry
            union = tuple(sorted(set().union(*by_url.values())))
            anchors = ((official, union),) + anchors
        else:
            candidates = tuple(("official", u) for u in cited)
        out[framework] = WatchEntry(framework, candidates, anchors=anchors)
    return out


def _tiers(candidates: tuple[tuple[str, str], ...]) -> list[tuple[str, list[str]]]:
    tiers: list[tuple[str, list[str]]] = []
    for via, url in candidates:
        if tiers and tiers[-1][0] == via:
            tiers[-1][1].append(url)
        else:
            tiers.append((via, [url]))
    return tiers


# --------------------------------------------------------------------------
# Normalisation + fetching
# --------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    _SKIP = frozenset({"script", "style"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    # Comments (and with them conditional comments) contribute nothing.
    def handle_comment(self, data: str) -> None:  # noqa: D401
        return None


def normalise(raw: bytes) -> str:
    """Visible text of a page: no script/style content, comments, tags or
    attributes (so no nonces or tokens in markup); entities unescaped;
    whitespace collapsed. Non-UTF-8 bytes are replaced, never fatal."""
    parser = _TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    parser.close()
    return " ".join(" ".join(parser.parts).split())


def content_hash(raw: bytes) -> str:
    return hashlib.sha256(normalise(raw).encode("utf-8")).hexdigest()


def _require_https(request: httpx.Request) -> None:
    # A request event hook runs for EVERY hop, redirects included, before
    # the request is sent — an http:// redirect target is refused unsent.
    if request.url.scheme != "https":
        raise FetchError(f"refused: https only (got {request.url})")


def build_http_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """The one outbound client configuration. Headers carry the
    User-Agent only — deliberately no platform auth header."""
    return httpx.Client(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        event_hooks={"request": [_require_https]},
        transport=transport,
    )


# The factory the default fetcher calls. tests/conftest.py replaces it with
# one that raises, so no test can reach the network by accident.
_client_factory: Callable[[], httpx.Client] = build_http_client


def default_fetcher(url: str) -> bytes:
    if not url.lower().startswith("https://"):
        raise FetchError(f"refused: https only ({url})")
    with _client_factory() as client:
        with client.stream("GET", url) as resp:
            if resp.url.scheme != "https":  # belt and braces behind the hook
                raise FetchError(f"refused: redirected off https ({resp.url})")
            if resp.status_code != 200:
                raise FetchError(f"HTTP {resp.status_code}")
            declared = resp.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_BYTES:
                raise FetchError(f"over the {MAX_BYTES}-byte cap "
                                 f"(content-length {declared})")
            buf = bytearray()
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
                if len(buf) > MAX_BYTES:
                    raise FetchError(f"over the {MAX_BYTES}-byte cap")
    return bytes(buf)


def _observe(framework: str, via: str, url: str, fetch: Fetcher,
             anchors: tuple[str, ...]) -> dict:
    base = {"framework": framework, "via": via, "url": url}
    try:
        raw = fetch(url)
        if not isinstance(raw, (bytes, bytearray)):
            raise FetchError(f"fetcher returned {type(raw).__name__}, not bytes")
        if len(raw) > MAX_BYTES:  # the cap binds injected fetchers too
            raise FetchError(f"over the {MAX_BYTES}-byte cap")
        raw = bytes(raw)
        text = normalise(raw)
        if not text:
            # A 200 with no visible text (an empty body, a script-only
            # interstitial) is not a reading of a regulation: unreachable,
            # never a "change" to an empty page.
            raise FetchError("no visible text in the response")
        if not anchors:
            raise FetchError("no anchor: no cited reference identifier is "
                             "derivable for this URL")
        if not has_anchor(text, anchors):
            # A 200 that names none of the cited references (a bot-challenge
            # or "verify you are human" page, a soft 404, a moved page) is
            # not a reading of the cited text: unreachable, never a change —
            # and never silently re-baselined after a clear.
            raise FetchError(f"anchor missing: none of {list(anchors)} in the response")
    except Exception as exc:  # noqa: BLE001 — any failure is "unreachable"
        return {**base, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    return {**base, "ok": True,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw)}


def _read_framework(entry: WatchEntry, fetch: Fetcher) -> tuple[str, list[dict], list[dict]]:
    """Walk the tiers: a tier is the reading as soon as ANY of its URLs
    answered (its failures stay as unreachable rows); a tier where nothing
    answered falls to the next tier and is reported as a fallback; the last
    tier is the reading even when nothing answered."""
    tiers = _tiers(entry.candidates)
    anchors = dict(entry.anchors)
    fallbacks: list[dict] = []
    for index, (via, urls) in enumerate(tiers):
        observations = [_observe(entry.framework, via, url, fetch, anchors.get(url, ()))
                        for url in urls]
        if any(o["ok"] for o in observations) or index == len(tiers) - 1:
            return via, observations, fallbacks
        fallbacks.extend({"via": o["via"], "url": o["url"], "error": o["error"]}
                         for o in observations)
    raise AssertionError("unreachable: a framework with candidates has tiers")


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Single flight: an HTTP-triggered check and a scheduler tick never fan out
# to the third-party hosts in parallel.
_CHECK_LOCK = threading.Lock()


def _compare(store: StaleStore, obs: dict, checked_at: str) -> tuple[dict, str | None]:
    """Compare one observation with the stored hash (inside the store
    transaction). Returns the report row and, on change, the flag reason."""
    row = {"url": obs["url"], "via": obs["via"]}
    if not obs["ok"]:
        return {**row, "status": "unreachable", "error": obs["error"]}, None
    prior = store.source_record(obs["url"])
    record = {
        "framework": obs["framework"],
        "via": obs["via"],
        "sha256": obs["sha256"],
        "raw_sha256": obs["raw_sha256"],
        "raw_bytes": obs["raw_bytes"],
        "first_seen": prior["first_seen"] if prior else checked_at,
        "last_seen": checked_at,
    }
    row.update(sha256_prefix=obs["sha256"][:12], raw_bytes=obs["raw_bytes"])
    reason = None
    if prior is None:
        row["status"] = "baseline"
    elif prior.get("sha256") == obs["sha256"]:
        row["status"] = "unchanged"
        if prior.get("changed_at"):
            record["changed_at"] = prior["changed_at"]
    else:
        byte_diff = obs["raw_bytes"] - int(prior.get("raw_bytes", 0))
        old = str(prior.get("sha256", ""))[:12]
        new = obs["sha256"][:12]
        reason = (f"{obs['url']} (normalised sha256 {old} -> {new}; byte diff "
                  f"{byte_diff:+d} raw bytes; via {obs['via']})")
        record["changed_at"] = checked_at
        record["previous_sha256"] = prior.get("sha256")
        row.update(status="changed", previous_sha256_prefix=old, byte_diff=byte_diff)
    store.put_source_record(obs["url"], record)
    return row, reason


def run_check(
    store: StaleStore | None = None,
    fetcher: Fetcher | None = None,
    *,
    trigger: str = "cli",
    now: datetime | None = None,
) -> dict:
    """Read every watched source, compare, flag changes, record the check.

    Fetching happens outside the store lock; the compare-flag-record step
    is one :meth:`StaleStore.transaction`, so it sees (and preserves) any
    clear persisted while the fetches were running."""
    store = store if store is not None else StaleStore()
    fetch = fetcher if fetcher is not None else default_fetcher
    with _CHECK_LOCK:
        entries = inventory()
        readings = {fw: _read_framework(entry, fetch)
                    for fw, entry in entries.items() if entry.candidates}
        checked_at = (now or _utc_now()).isoformat()
        rows: list[dict] = []
        flagged: list[str] = []
        unreachable: list[str] = []
        with store.transaction():
            for framework in FRAMEWORKS:
                entry = entries[framework]
                if not entry.candidates:
                    rows.append({"framework": framework, "status": "no-source",
                                 "reason": entry.no_source_reason,
                                 "fetched_via": None, "sources": [],
                                 "fallbacks": []})
                    continue
                via, observations, fallbacks = readings[framework]
                sources, reasons = [], []
                for obs in observations:
                    row, reason = _compare(store, obs, checked_at)
                    sources.append(row)
                    if reason:
                        reasons.append(reason)
                    if row["status"] == "unreachable":
                        unreachable.append(row["url"])
                statuses = {s["status"] for s in sources}
                if reasons:
                    store.apply_mark(framework, "regwatch content change: "
                                     + "; ".join(reasons))
                    flagged.append(framework)
                    status = "changed"
                elif statuses == {"unreachable"}:
                    status = "unreachable"
                elif "baseline" in statuses:
                    status = "baseline"
                else:
                    status = "unchanged"
                rows.append({"framework": framework, "status": status,
                             "fetched_via": via if status != "unreachable" else None,
                             "sources": sources, "fallbacks": fallbacks})
            active = {f["framework"] for f in store.active()}
            for row in rows:
                row["flag_active"] = row["framework"] in active
            if flagged:
                exit_code = EXIT_CHANGED
            elif unreachable:
                exit_code = EXIT_UNREACHABLE
            else:
                exit_code = EXIT_UNCHANGED
            store.set_last_check({
                "checked_at": checked_at,
                "trigger": trigger,
                "exit_code": exit_code,
                "frameworks": {r["framework"]: r["status"] for r in rows},
                "flagged": flagged,
                "unreachable": unreachable,
            })
    return {
        "checked_at": checked_at,
        "trigger": trigger,
        "exit_code": exit_code,
        "frameworks": rows,
        "flagged": flagged,
        "unreachable": unreachable,
    }


def inventory_report(store: StaleStore | None = None) -> dict:
    """What ``regwatch check`` would read, with the stored hashes — no
    network. The CLI prints this without ``--fetch``. Each candidate also
    shows how its stored reading was taken (``stored_via``: ``official``,
    ``mirror`` or ``manual:<NAME>``) and, for a manual reading, who saved the
    file and its sha256: ``last_check`` records only automated checks, so this
    is where a ``check-file`` reading stays visible."""
    store = store if store is not None else StaleStore()
    rows = []
    for framework, entry in inventory().items():
        if not entry.candidates:
            rows.append({"framework": framework, "status": "no-source",
                         "reason": entry.no_source_reason, "candidates": []})
            continue
        candidates = []
        anchors = dict(entry.anchors)
        for via, url in entry.candidates:
            record = store.source_record(url) or {}
            candidates.append({
                "via": via, "url": url, "anchors": list(anchors.get(url, ())),
                "stored_sha256_prefix": (record.get("sha256") or "")[:12] or None,
                "last_seen": record.get("last_seen"),
                "stored_via": record.get("via"),
                "fetched_by": record.get("fetched_by"),
                "file_sha256": record.get("file_sha256"),
            })
        rows.append({"framework": framework, "candidates": candidates})
    return {"frameworks": rows, "last_check": store.last_check()}


# --------------------------------------------------------------------------
# Manual path: a page a named human saved from a browser (check-file)
# --------------------------------------------------------------------------
#
# Don, 2026-09-13: OSFI answers HTTP 403 to the honest crosswalk User-Agent,
# and spoofing a browser UA is bot-detection evasion — so OSFI E-23 is read by
# a human instead. The human saves the page as HTML; ``check_file`` hashes it
# with the SAME normalisation and anchor rule as a fetch (``_observe``) and
# compares/flags through the SAME ``_compare`` + ``apply_mark`` in one store
# transaction. It proves only what the named human saved: the bytes are
# whatever the browser wrote, and nothing here can tell that they came from
# the cited URL. The human's name is recorded as ``via: manual:<NAME>`` and
# the file's sha256 is kept with the reading.

MANUAL_SUFFIXES = (".html", ".htm")
# Browsers put a "saved from url" comment and whitespace ahead of the markup.
MANUAL_SNIFF_BYTES = 64 * 1024
_HTML_MARK = re.compile(rb"<!doctype\s+html|<html[\s>]", re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
#: Unicode categories refused anywhere in a --fetched-by name: controls (C0,
#: DEL, C1 incl. NEL), format characters (zero-width space/joiners, BOM,
#: bidi overrides) and the line/paragraph separators — all invisible or
#: line-breaking, so a record could name someone other than it appears to.
_REFUSED_NAME_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


class ManualFileRefused(ValueError):
    """``check-file`` refused its input. Nothing was read into the store and
    no flag was set or cleared."""


def read_manual_file(path: str | Path) -> bytes:
    """The bytes of a browser-saved HTML page, or :class:`ManualFileRefused`.

    Refused, by name: a name without an .html/.htm suffix (a PDF, MHTML,
    text or screenshot is not the page as served), a path that is not a
    regular file, an empty file, a file over the fetch cap (``MAX_BYTES``,
    checked before reading and again on the bytes read), and content with
    no ``<!doctype html>`` / ``<html`` in its first 64 KiB or with NUL bytes
    there (binary, or a UTF-16 save the normaliser cannot read)."""
    path = Path(path)
    if path.suffix.lower() not in MANUAL_SUFFIXES:
        raise ManualFileRefused(
            f"not HTML: {path.name!r} — save the page from the browser as HTML "
            f"({'/'.join(MANUAL_SUFFIXES)}), not PDF, MHTML, text or an image")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ManualFileRefused(f"cannot read {path}: {exc.strerror or exc}") from None
    if not path.is_file():
        raise ManualFileRefused(f"not a regular file: {path}")
    if size > MAX_BYTES:
        raise ManualFileRefused(
            f"over the {MAX_BYTES}-byte cap: {path} is {size} bytes")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)  # the file may have grown since stat
    if not raw:
        raise ManualFileRefused(f"empty file: {path}")
    if len(raw) > MAX_BYTES:
        raise ManualFileRefused(f"over the {MAX_BYTES}-byte cap: {path}")
    head = raw[:MANUAL_SNIFF_BYTES]
    if b"\x00" in head:
        raise ManualFileRefused(
            f"not HTML: {path.name!r} carries NUL bytes (binary, or a UTF-16 "
            f"save) — save it as HTML in UTF-8")
    if not _HTML_MARK.search(head):
        raise ManualFileRefused(
            f"not HTML: no <!doctype html> or <html> in the first "
            f"{MANUAL_SNIFF_BYTES // 1024} KiB of {path.name!r}")
    return raw


def _named_human(fetched_by: str | None) -> str:
    name = (fetched_by or "").strip()
    if not name:
        raise ManualFileRefused("--fetched-by must name the human who saved the "
                                "page — a manual reading is NAMED")
    if _CONTROL_CHARS.search(name) or any(
            unicodedata.category(ch) in _REFUSED_NAME_CATEGORIES for ch in name):
        raise ManualFileRefused("--fetched-by must be a plain name (no control "
                                "characters, invisible format characters or "
                                "line breaks)")
    if not any(ch.isalnum() for ch in name):
        raise ManualFileRefused("--fetched-by must name a human: it needs at "
                                "least one letter or digit")
    return name


def check_file(
    framework: str,
    path: str | Path,
    fetched_by: str,
    *,
    url: str | None = None,
    store: StaleStore | None = None,
    now: datetime | None = None,
) -> dict:
    """Record a browser-saved page as a reading of one watched URL.

    Same hash target (``normalise``), same anchor rule, same compare and
    flag as :func:`run_check`: the first reading of the URL is ``baseline``
    (no flag), an identical one ``unchanged``, a different one ``changed`` —
    ``apply_mark`` with the reason naming ``via manual:<NAME>``. ``url``
    defaults to the framework's only watched URL and must be one of them.
    Refusals (:class:`ManualFileRefused`, nothing written): unknown or
    no-source framework, ambiguous or unwatched ``url``, a blank name, a file
    that is not HTML / empty / over the cap, and a page that is not a reading
    (no visible text, or none of the cited reference identifiers — a saved
    challenge page or the wrong page). ``last_check`` is NOT touched: it
    stays the record of the last automated check. Returns the report;
    ``exit_code`` is 3 when a flag was set, else 0."""
    name = _named_human(fetched_by)
    entries = inventory()
    if framework not in entries:
        raise ManualFileRefused(
            f"unknown framework {framework!r}; known: {sorted(entries)}")
    entry = entries[framework]
    if not entry.candidates:
        raise ManualFileRefused(
            f"{framework} is no-source ({entry.no_source_reason}): no page is "
            f"cited, so there is nothing to compare a file with")
    watched = [candidate_url for _via, candidate_url in entry.candidates]
    if url is None:
        if len(watched) != 1:
            raise ManualFileRefused(
                f"{framework} watches {len(watched)} URLs; pass --url, one of: "
                + ", ".join(watched))
        url = watched[0]
    elif url not in watched:
        raise ManualFileRefused(
            f"{url!r} is not watched for {framework}; one of: " + ", ".join(watched))
    raw = read_manual_file(path)
    via = f"manual:{name}"
    obs = _observe(framework, via, url, lambda _url: raw, dict(entry.anchors).get(url, ()))
    if not obs["ok"]:
        raise ManualFileRefused(
            f"{Path(path).name!r} is not a reading of {url}: {obs['error']} — "
            f"was a challenge page or the wrong page saved?")
    file_sha256 = hashlib.sha256(raw).hexdigest()
    checked_at = (now or _utc_now()).isoformat()
    store = store if store is not None else StaleStore()
    with store.transaction():
        row, reason = _compare(store, obs, checked_at)
        record = store.source_record(url) or {}
        record.update(file_sha256=file_sha256, fetched_by=name)
        store.put_source_record(url, record)
        if reason:
            store.apply_mark(framework, "regwatch content change (manual file): " + reason)
        flag_active = any(f["framework"] == framework for f in store.active())
    return {
        "framework": framework,
        "checked_at": checked_at,
        "trigger": "manual",
        "fetched_via": via,
        "file": str(path),
        "file_sha256": file_sha256,
        **row,
        "flag_active": flag_active,
        "exit_code": EXIT_CHANGED if reason else EXIT_UNCHANGED,
    }


# --------------------------------------------------------------------------
# Scheduler (crosswalk serve --every / FIELD_CROSSWALK_EVERY)
# --------------------------------------------------------------------------

def run_every(
    fn: Callable[[], Any],
    seconds: float,
    stop_event: threading.Event,
    sleep: Callable[[float], Any] | None = None,
) -> int:
    """Call ``fn`` every ``seconds`` until ``stop_event`` is set. The first
    tick fires AFTER the first interval. A raising ``fn`` is logged and the
    loop continues. ``sleep`` is injectable for tests; the default waits on
    the stop event so shutdown is immediate. Returns the ticks fired."""
    wait = sleep if sleep is not None else stop_event.wait
    ticks = 0
    while not stop_event.is_set():
        wait(seconds)
        if stop_event.is_set():
            break
        ticks += 1
        try:
            fn()
        except Exception:  # noqa: BLE001 — never let a tick kill the thread
            log.exception("crosswalk regwatch scheduler: tick raised; continuing")
    return ticks


def scheduled_check(store_factory: Callable[[], StaleStore],
                    fetcher: Fetcher | None = None) -> dict | None:
    """One scheduler tick: a full check with ``trigger='scheduler'``.
    Exceptions are swallowed and logged — the scheduler must survive a bad
    day at a third-party host or a transient store error."""
    try:
        report = run_check(store_factory(), fetcher, trigger="scheduler")
    except Exception:  # noqa: BLE001
        log.exception("crosswalk regwatch scheduled check failed")
        return None
    log.info("crosswalk regwatch scheduled check: exit %s, flagged %s, "
             "unreachable %s", report["exit_code"], report["flagged"] or "none",
             report["unreachable"] or "none")
    return report
